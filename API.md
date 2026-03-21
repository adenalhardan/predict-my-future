# Predict My Future — API & Architecture

## End-to-End Flow

### Step 1 — Get Upload URL

```
GET /api/get-presigned-url
```

Returns a signed GCS upload URL and a `job_id`.

```json
{ "job_id": "abc-123", "upload_url": "https://storage.googleapis.com/..." }
```

### Step 2 — Upload Video to GCS

```
PUT {upload_url}
Content-Type: video/mp4
Body: <raw video bytes>
```

Video lands at `gs://seecircle-cdn/predict-future/inputs/{job_id}/video.mp4`. Server is not involved.

### Step 3 — Start Pipeline

```
POST /api/predict/start
Content-Type: application/json
Body: { "job_id": "abc-123" }
```

Server downloads the video from GCS, launches the background pipeline, returns immediately.

### Step 4 — Poll for Results

```
GET /api/poll?job_id=abc-123
```

While processing:

```json
{ "status": "processing" }
```

When done:

```json
{
  "status": "completed",
  "prediction": {
    "id": "abc-123",
    "scene_analysis": "{...}",
    "scenarios": [
      {
        "type": "positive",
        "title": "Eureka Moment",
        "description": "The team agrees on a brilliant idea",
        "video_url": "https://storage.googleapis.com/.../positive.mp4?X-Goog-Signature=..."
      },
      { "type": "bad", "..." : "..." },
      { "type": "insane", "..." : "..." },
      { "type": "funny", "..." : "..." }
    ]
  }
}
```

### Step 5 — Play Videos

Each `video_url` is a signed GCS URL valid for 1 hour. Client loads them directly.

---

## Background Pipeline (what happens inside Step 3)

### Stage A — Scene Analysis

- Sends video to **Gemini 2.5 Flash**
- Returns structured JSON: `{ people, actions, setting, mood, key_objects }`

### Stage B — Prompt Generation

- Sends scene analysis to **Gemini 2.5 Flash**
- Returns 4 scenario prompts: `positive`, `bad`, `insane`, `funny`
- Each has: `type`, `title`, `description`, `visual_description`

### Stage C — Video Generation (per scenario, sequential)

1. Extract last frame from original video (OpenCV)
2. Call **Veo 3.1** with `visual_description` + reference frame (9:16, 8s)
3. Poll Veo operation until done (~1-2 min)
4. Download raw generated video
5. **ffmpeg concat**: last 5s of original + Veo output → seamless clip (720x1280 @ 24fps)
6. Save locally to `test_videos/generated/{job_id}/{type}.mp4`
7. Upload to GCS at `predict-future/outputs/{job_id}/{type}.mp4`
8. Generate signed download URL for client

---

## GCS File Structure

```
gs://seecircle-cdn/predict-future/
├── inputs/{job_id}/video.mp4            ← uploaded by client
└── outputs/{job_id}/
    ├── positive.mp4                      ← last 5s of original + Veo output
    ├── bad.mp4
    ├── insane.mp4
    └── funny.mp4
```

---

## All Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/` | Health check |
| `GET` | `/api/get-presigned-url` | Get signed upload URL + job_id |
| `POST` | `/api/predict/start` | Start pipeline (video already in GCS) |
| `POST` | `/api/predict` | Start pipeline (multipart upload, for testing) |
| `GET` | `/api/poll?job_id=...` | Poll job status |
| `POST` | `/api/test/analyze` | Test: scene analysis only |
| `POST` | `/api/test/prompts` | Test: scene analysis + prompts only |

---

## Env Vars

| Variable | Purpose |
|----------|---------|
| `GOOGLE_CLOUD_PROJECT` | GCP project ID |
| `GOOGLE_API_KEY` | Gemini / Veo API key |
| `GCS_BUCKET` | Bucket name (`seecircle-cdn`) |
| `GCP_CLIENT_EMAIL` | Service account email (for signed URLs) |
| `GCP_PRIVATE_KEY` | Service account private key (for signed URLs) |
| `MAX_VIDEOS` | Number of scenario videos to generate (1–4) |

---

## Services

| Service | Model / Tool | What it does |
|---------|-------------|--------------|
| GCS | `google-cloud-storage` | Signed URLs, video storage |
| Gemini | `gemini-2.5-flash` | Scene analysis + prompt generation |
| Veo | `veo-3.1-generate-preview` | Video generation from prompt + reference frame |
| OpenCV | `opencv-python-headless` | Extract last frame from input video |
| ffmpeg | system binary | Concat original tail + generated video |

---

## Scenario Types

| Type | Description |
|------|-------------|
| `positive` | Most likely positive outcome |
| `bad` | Negative or unfortunate (awkward, not violent) |
| `insane` | Wild, surreal, over-the-top (not dangerous) |
| `funny` | Hilarious, comedic |
