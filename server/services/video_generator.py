import os
import asyncio
import tempfile
from pathlib import Path
from google.genai import types
from PIL import Image
from models.schemas import ScenarioPrompt
from services.client import get_client


VEO_MODEL = "veo-2.0-generate-001"

OUTPUT_DIR = Path(tempfile.gettempdir()) / "predict-my-future" / "videos"
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


async def generate_video(
    scenario: ScenarioPrompt,
    reference_image: Image.Image,
    job_id: str,
) -> str:
    """Generate a single scenario video with Veo 2 and return its file path."""
    client = get_client()
    operation = client.models.generate_videos(
        model=VEO_MODEL,
        prompt=scenario.visual_description,
        image=reference_image,
        config=types.GenerateVideosConfig(
            aspect_ratio="9:16",
            number_of_videos=1,
        ),
    )

    while not operation.done:
        await asyncio.sleep(5)
        operation = client.operations.get(operation)

    video_path = OUTPUT_DIR / f"{job_id}_{scenario.type}.mp4"
    generated = operation.result.generated_videos[0]
    video_data = client.files.download(file=generated.video)
    video_path.write_bytes(video_data)

    return str(video_path)


async def generate_all_videos(
    scenarios: list[ScenarioPrompt],
    video_bytes: bytes,
    job_id: str,
) -> list[str]:
    """Generate all 4 scenario videos in parallel. Returns list of file paths."""
    reference_image = extract_last_frame(video_bytes)

    paths = await asyncio.gather(*[
        generate_video(scenario, reference_image, job_id)
        for scenario in scenarios
    ])

    return list(paths)
