import uuid
import asyncio
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException
from pydantic import BaseModel
from models.schemas import (
    PredictionResponse,
    Scenario,
    JobStatus,
)
from services.scene_analyzer import analyze_scene
from services.prompt_generator import generate_prompts
from services.video_generator import generate_all_videos
from services.storage import (
    is_gcs_enabled,
    download_bytes_from_gcs,
    generate_download_signed_url,
)

router = APIRouter(prefix="/api")

# In-memory job store (swap for Redis/DB in production)
jobs: dict[str, JobStatus] = {}


async def _run_prediction(job_id: str, video_bytes: bytes, mime_type: str):
    """Background task: runs the full prediction pipeline."""
    try:
        jobs[job_id] = JobStatus(status="processing")

        scene = await analyze_scene(video_bytes, mime_type)

        prompts = await generate_prompts(scene)

        results = await generate_all_videos(
            prompts.scenarios, video_bytes, job_id
        )

        scenarios = []
        for prompt, path in results:
            if not path:
                video_url = ""
            elif is_gcs_enabled():
                video_url = generate_download_signed_url(
                    f"outputs/{job_id}_{prompt.type}.mp4"
                )
            else:
                video_url = f"/api/videos/{job_id}_{prompt.type}.mp4"

            scenarios.append(
                Scenario(
                    type=prompt.type,
                    title=prompt.title,
                    description=prompt.description,
                    video_url=video_url,
                )
            )

        jobs[job_id] = JobStatus(
            status="completed",
            prediction=PredictionResponse(
                id=job_id,
                scene_analysis=scene.model_dump_json(),
                scenarios=scenarios,
            ),
        )
    except Exception as e:
        jobs[job_id] = JobStatus(status="failed", error=str(e))


@router.post("/predict")
async def predict(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
):
    """Upload a video and start the prediction pipeline.

    Returns a job_id to poll for results.
    """
    job_id = str(uuid.uuid4())
    video_bytes = await video.read()
    mime_type = _resolve_mime_type(video)

    jobs[job_id] = JobStatus(status="pending")
    background_tasks.add_task(_run_prediction, job_id, video_bytes, mime_type)

    return {"job_id": job_id}


def _resolve_mime_type(upload: UploadFile) -> str:
    """Determine the correct MIME type from the upload or filename."""
    ct = upload.content_type
    if ct and ct != "application/octet-stream":
        return ct
    name = (upload.filename or "").lower()
    if name.endswith(".mp4"):
        return "video/mp4"
    if name.endswith(".mov"):
        return "video/quicktime"
    if name.endswith(".webm"):
        return "video/webm"
    return "video/mp4"


class StartRequest(BaseModel):
    job_id: str


@router.post("/predict/start")
async def predict_start(
    body: StartRequest,
    background_tasks: BackgroundTasks,
):
    """Start the prediction pipeline for a video already uploaded to GCS.

    The client must first call GET /api/get-presigned-url, upload the video
    using the returned upload_url, then call this endpoint with the job_id.
    """
    if not is_gcs_enabled():
        raise HTTPException(status_code=503, detail="GCS not configured")

    job_id = body.job_id
    blob_path = f"inputs/{job_id}/video.mp4"

    try:
        video_bytes = download_bytes_from_gcs(blob_path)
    except Exception as e:
        raise HTTPException(
            status_code=404,
            detail=f"Video not found in GCS. Did you upload it? ({e})",
        )

    jobs[job_id] = JobStatus(status="pending")
    background_tasks.add_task(_run_prediction, job_id, video_bytes, "video/mp4")

    return {"job_id": job_id}


@router.post("/test/analyze")
async def test_analyze(video: UploadFile = File(...)):
    """Test endpoint: only runs scene analysis (step 2). No video generation."""
    video_bytes = await video.read()
    mime_type = _resolve_mime_type(video)
    scene = await analyze_scene(video_bytes, mime_type)
    return {"scene_analysis": scene.model_dump()}


@router.post("/test/prompts")
async def test_prompts(video: UploadFile = File(...)):
    """Test endpoint: runs scene analysis + prompt generation (steps 2-3). No video generation."""
    video_bytes = await video.read()
    mime_type = _resolve_mime_type(video)
    scene = await analyze_scene(video_bytes, mime_type)
    prompts = await generate_prompts(scene)
    return {
        "scene_analysis": scene.model_dump(),
        "scenarios": [s.model_dump() for s in prompts.scenarios],
    }


@router.get("/poll")
async def poll(job_id: str):
    """Poll for prediction job status."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]

    if job.status == "completed":
        return {"status": "completed", "prediction": job.prediction}
    elif job.status == "failed":
        return {"status": "failed", "error": job.error}
    else:
        return {"status": job.status}
