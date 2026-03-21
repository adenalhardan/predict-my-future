from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from models.schemas import (
    JobStatus,
    PredictionResponse,
    Scenario,
)
from services.prompt_generator import generate_prompts
from services.scene_analyzer import analyze_scene
from services.storage import (
    download_bytes_from_gcs,
    is_gcs_enabled,
    resolve_cdn_url,
)
from services.video_generator import generate_all_videos

router = APIRouter(prefix="/api")

# In-memory job store (swap for Redis/DB in production)
jobs: dict[str, JobStatus] = {}


async def _run_prediction(job_id: str, video_bytes: bytes, mime_type: str):
    """Background task: runs the full prediction pipeline."""
    try:
        jobs[job_id] = JobStatus(status="processing")

        scene = await analyze_scene(video_bytes, mime_type)

        prompts = await generate_prompts(scene)

        results = await generate_all_videos(prompts.scenarios, video_bytes, job_id)

        scenarios = []
        for prompt, path in results:
            if not path:
                video_url = ""
            elif is_gcs_enabled():
                video_url = resolve_cdn_url(f"outputs/{job_id}/{prompt.type}.mp4")
            else:
                video_url = f"/api/videos/{job_id}/{prompt.type}.mp4"

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
