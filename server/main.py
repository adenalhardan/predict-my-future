from pathlib import Path

from dotenv.main import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from routes.predict import router as predict_router

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
import tempfile

video_dir = Path(tempfile.gettempdir()) / "predict-my-future" / "videos"
video_dir.mkdir(parents=True, exist_ok=True)
app.mount("/api/videos", StaticFiles(directory=str(video_dir)), name="videos")


@app.get("/")
async def health():
    return {"status": "ok", "service": "predict-my-future"}


@app.get("/api/get-presigned-url")
async def get_presigned_url():
    return "TODO"
