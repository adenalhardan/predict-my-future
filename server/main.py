import uuid
from pathlib import Path

from dotenv.main import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from routes.predict import router as predict_router
from services.storage import generate_upload_signed_url, is_gcs_enabled

load_dotenv()

app = FastAPI(title="Predict My Future")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(predict_router)

# Serve generated videos as static files
video_dir = Path(__file__).resolve().parent / "test_videos" / "generated"
video_dir.mkdir(parents=True, exist_ok=True)
app.mount("/api/videos", StaticFiles(directory=str(video_dir)), name="videos")

# Serve test input videos and demo page
test_dir = Path(__file__).resolve().parent / "test_videos"
app.mount("/test", StaticFiles(directory=str(test_dir), html=True), name="test")


@app.get("/")
async def health():
    return {"status": "ok", "service": "predict-my-future"}


@app.get("/api/get-presigned-url")
async def get_presigned_url():
    """Return a signed upload URL so the client can PUT a video directly to GCS."""
    if not is_gcs_enabled():
        raise HTTPException(status_code=503, detail="GCS not configured")

    job_id = str(uuid.uuid4())
    blob_path = f"inputs/{job_id}/video.mp4"
    upload_url = generate_upload_signed_url(blob_path)

    return {"job_id": job_id, "upload_url": upload_url}
