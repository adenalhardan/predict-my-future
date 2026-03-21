import os
import io
import asyncio
import time
import tempfile
from pathlib import Path
import httpx
from google.genai import types
from PIL import Image
from models.schemas import ScenarioPrompt
from services.client import get_client


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
    job_id: str,
) -> str:
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
            duration_seconds=6,
        ),
    )

    result = poll_operation(operation.name, api_key)

    video_path = OUTPUT_DIR / f"{job_id}_{scenario.type}.mp4"

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
    video_path.write_bytes(video_resp.content)
    print(f"[Veo] Saved video to: {video_path}")

    return str(video_path)


async def generate_video(
    scenario: ScenarioPrompt,
    reference_image: types.Image,
    job_id: str,
) -> "str | None":
    """Async wrapper around sync Veo generation."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, generate_video_sync, scenario, reference_image, job_id
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

    results = []
    for scenario in scenarios:
        try:
            path = await generate_video(scenario, reference_image, job_id)
        except Exception as e:
            print(f"[Veo] Error generating '{scenario.type}': {e}")
            path = None
        results.append((scenario, path))

    return results
