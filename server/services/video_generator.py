import os
import io
import asyncio
import subprocess
import time
import tempfile
from pathlib import Path
import httpx
from google.genai import types
from PIL import Image
from models.schemas import ScenarioPrompt
from services.client import get_client
from services.storage import is_gcs_enabled, upload_bytes_to_gcs


VEO_MODEL = "veo-3.1-generate-preview"
BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "test_videos" / "generated"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def extract_last_frame(video_bytes: bytes) -> Image.Image:
    """Extract the last frame from a video as a PIL Image.

    Uses opencv if available, otherwise returns a black placeholder.
    """
    try:
        import cv2

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(video_bytes)
            tmp_path = f.name

        cap = cv2.VideoCapture(tmp_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames - 1)
        ret, frame = cap.read()
        cap.release()
        os.unlink(tmp_path)

        if ret:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            return Image.fromarray(frame_rgb)
    except ImportError:
        pass

    return Image.new("RGB", (1280, 720), color=(0, 0, 0))


def pil_to_genai_image(pil_image: Image.Image) -> types.Image:
    """Convert a PIL Image to a google-genai Image with base64 bytes."""
    buf = io.BytesIO()
    pil_image.save(buf, format="PNG")
    image_bytes = buf.getvalue()
    return types.Image(image_bytes=image_bytes, mime_type="image/png")


TAIL_SECONDS = 5


def concat_with_original_tail(
    original_video_bytes: bytes,
    generated_video_path: str,
    output_path: str,
) -> str:
    """Prepend the last TAIL_SECONDS of the original video to the generated video."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(original_video_bytes)
        original_tmp = f.name

    tail_tmp = tempfile.mktemp(suffix=".mp4")
    scaled_tmp = tempfile.mktemp(suffix=".mp4")

    try:
        # 1. Extract last N seconds of original, re-encode to consistent format
        subprocess.run(
            [
                "ffmpeg", "-y", "-sseof", f"-{TAIL_SECONDS}",
                "-i", original_tmp,
                "-vf", "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:-1:-1",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-r", "24", "-an", tail_tmp,
            ],
            capture_output=True, check=True,
        )
        print(f"[ffmpeg] Extracted last {TAIL_SECONDS}s of original")

        # 2. Re-encode generated video to match resolution/framerate
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", generated_video_path,
                "-vf", "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:-1:-1",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-r", "24", "-an", scaled_tmp,
            ],
            capture_output=True, check=True,
        )
        print("[ffmpeg] Re-encoded generated video")

        # 3. Concatenate using concat demuxer
        concat_list = tempfile.mktemp(suffix=".txt")
        with open(concat_list, "w") as cl:
            cl.write(f"file '{tail_tmp}'\nfile '{scaled_tmp}'\n")

        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_list,
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                output_path,
            ],
            capture_output=True, check=True,
        )
        print(f"[ffmpeg] Concatenated -> {output_path}")

        return output_path
    finally:
        for p in [original_tmp, tail_tmp, scaled_tmp]:
            if os.path.exists(p):
                os.unlink(p)
        concat_list_path = concat_list if 'concat_list' in dir() else None
        if concat_list_path and os.path.exists(concat_list_path):
            os.unlink(concat_list_path)


def poll_operation(operation_name: str, api_key: str) -> dict:
    """Poll a long-running operation via REST API with API key auth."""
    url = f"{BASE_URL}/{operation_name}"
    print(f"[Veo] Polling operation: {url}")

    while True:
        resp = httpx.get(url, params={"key": api_key}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        print(f"[Veo] Poll status: done={data.get('done', False)}")

        if data.get("done"):
            return data

        time.sleep(10)


def generate_video_sync(
    scenario: ScenarioPrompt,
    reference_image: types.Image,
    original_video_bytes: bytes,
    job_id: str,
) -> "str | None":
    """Generate a single scenario video with Veo 3.1 (sync, for use in thread)."""
    client = get_client()
    api_key = os.getenv("GOOGLE_API_KEY")

    operation = client.models.generate_videos(
        model=VEO_MODEL,
        prompt=scenario.visual_description,
        image=reference_image,
        config=types.GenerateVideosConfig(
            aspect_ratio="9:16",
            number_of_videos=1,
            duration_seconds=8,
            person_generation="allow_adult",
        ),
    )

    result = poll_operation(operation.name, api_key)

    gen_response = result.get("response", {})
    veo_response = gen_response.get("generateVideoResponse", gen_response)

    rai_count = veo_response.get("raiMediaFilteredCount", 0)
    if rai_count:
        reasons = veo_response.get("raiMediaFilteredReasons", [])
        print(f"[Veo] Safety filter blocked video for '{scenario.type}': {reasons}")
        return None

    generated_samples = veo_response.get("generatedSamples", veo_response.get("generatedVideos", []))
    if not generated_samples:
        print(f"[Veo] No videos returned for '{scenario.type}': {result}")
        return None

    video_uri = generated_samples[0]["video"]["uri"]
    separator = "&" if "?" in video_uri else "?"
    download_url = f"{video_uri}{separator}key={api_key}"
    print(f"[Veo] Downloading video from: {video_uri}")
    video_resp = httpx.get(download_url, timeout=120, follow_redirects=True)
    video_resp.raise_for_status()

    # Save raw Veo output to temp file, then concat with original tail
    raw_path = OUTPUT_DIR / f"{job_id}_{scenario.type}_raw.mp4"
    raw_path.write_bytes(video_resp.content)
    print(f"[Veo] Saved raw Veo video to: {raw_path}")

    final_path = str(OUTPUT_DIR / f"{job_id}_{scenario.type}.mp4")
    concat_with_original_tail(original_video_bytes, str(raw_path), final_path)
    raw_path.unlink(missing_ok=True)

    if is_gcs_enabled():
        final_bytes = Path(final_path).read_bytes()
        gcs_blob = f"outputs/{job_id}_{scenario.type}.mp4"
        upload_bytes_to_gcs(gcs_blob, final_bytes)

    return final_path


async def generate_video(
    scenario: ScenarioPrompt,
    reference_image: types.Image,
    original_video_bytes: bytes,
    job_id: str,
) -> "str | None":
    """Async wrapper around sync Veo generation."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, generate_video_sync, scenario, reference_image, original_video_bytes, job_id
    )


async def generate_all_videos(
    scenarios: list[ScenarioPrompt],
    video_bytes: bytes,
    job_id: str,
) -> "list[tuple[ScenarioPrompt, str | None]]":
    """Generate all 4 scenario videos sequentially to avoid rate limits.

    Returns list of (scenario, path_or_none) tuples.
    """
    pil_frame = extract_last_frame(video_bytes)
    reference_image = pil_to_genai_image(pil_frame)

    max_videos = int(os.getenv("MAX_VIDEOS", "4"))
    results = []
    for scenario in scenarios[:max_videos]:
        try:
            path = await generate_video(scenario, reference_image, video_bytes, job_id)
        except Exception as e:
            print(f"[Veo] Error generating '{scenario.type}': {e}")
            path = None
        results.append((scenario, path))

    return results
