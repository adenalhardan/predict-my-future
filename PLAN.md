# Predict My Future — Project Plan

## Concept

An iPhone app where a user records a short video of a real-life situation, and the app generates **4 different future scenario videos** showing what could happen next:

| # | Scenario | Example (judges + friend at desk) |
|---|----------|-----------------------------------|
| 1 | **Most Likely (Positive)** | They shake hands, everyone smiles |
| 2 | **Bad Scenario** | Judges look extremely bored, awkward silence |
| 3 | **Insane Scenario** | One judge slaps your friend |
| 4 | **Funny Scenario** | Your friend falls off the chair |

---

## Architecture Overview

```
┌─────────────┐        ┌──────────────────────────────────┐       ┌─────────────────┐
│   iOS App   │──POST──▶   Python Server (FastAPI)         │──────▶│  Google Gemini   │
│  (SwiftUI)  │◀──JSON──│        /api/predict              │       │  (Scene Analysis │
│             │         │                                  │──────▶│   + Prompting)   │
│  • Record   │         │  1. Receive video                │       └─────────────────┘
│  • Upload   │         │  2. Analyze scene (Gemini)       │
│  • Display  │         │  3. Generate 4 prompts           │       ┌─────────────────┐
│    results  │         │  4. Generate 4 videos (Veo)      │──────▶│  Google Veo 2    │
│             │         │  5. Return video URLs             │       │  (Video Gen)     │
└─────────────┘         └──────────────────────────────────┘       └─────────────────┘
```

---

## Endpoints 

* GET /api/get-presigned-url : returns a presigned URL for the Azure storage bucket
* GET /api/predict?job_id={job_id} : start predict job, the job_id is used to resolve the path of the image
* GET /api/poll?job_id={job_id} : poll job status, either returns {status: pending} or all of the completed job data

## Project Structure

```
predict-my-future/
├── server/                        # Python backend (FastAPI)
│   ├── main.py                    # FastAPI app entry point + uvicorn
│   ├── routes/
│   │   └── predict.py             # POST /api/predict — main pipeline
│   ├── services/
│   │   ├── scene_analyzer.py      # Gemini: analyze video, understand context
│   │   ├── prompt_generator.py    # Gemini: generate 4 scenario prompts
│   │   └── video_generator.py     # Veo 2: generate 4 videos
│   ├── models/
│   │   └── schemas.py             # Pydantic models (request/response)
│   ├── requirements.txt
│   └── .env                       # API keys (GOOGLE_API_KEY, etc.)
│
├── app/                           # iOS App (SwiftUI)
│   └── PredictMyFuture/
│       ├── PredictMyFutureApp.swift
│       ├── Views/
│       │   ├── CameraView.swift         # Video recording screen
│       │   ├── ResultsView.swift        # 4 scenario videos grid
│       │   └── ScenarioCardView.swift   # Single scenario video player
│       ├── ViewModels/
│       │   ├── CameraViewModel.swift    # Camera capture logic
│       │   └── PredictionViewModel.swift # API calls, state management
│       ├── Services/
│       │   └── APIService.swift         # HTTP client for server
│       ├── Models/
│       │   └── Prediction.swift         # Data models
│       └── Assets.xcassets/
│
├── PLAN.md                        # This file
└── .gitignore
```

---

## Tech Stack

### Server: Python + FastAPI + google-genai

| Component | Choice | Why |
|-----------|--------|-----|
| Framework | **FastAPI** | Async-native, auto-generated docs at `/docs`, file upload support, Pydantic validation |
| AI SDK | **google-genai** | Google's primary SDK — one package for both Gemini and Veo 2 |
| Video processing | **Pillow** | Extract last frame from uploaded video for Veo 2 reference image |
| Structured output | **Pydantic** | Type-safe models that double as Gemini response schemas |
| Async parallel gen | **asyncio.gather()** | Fire all 4 Veo 2 calls simultaneously |

**Key advantage**: One SDK (`google-genai`) handles the entire pipeline — scene analysis, prompt generation, AND video generation.

### Google Gemini — What models?

| Step | Model | Why |
|------|-------|-----|
| Scene Analysis | **Gemini 2.5 Flash** | Fast, multimodal (understands video), cheap |
| Prompt Generation | **Gemini 2.5 Flash** | Creative text generation, can be same call as analysis |
| Video Generation | **Veo 2** (via `google-genai`) | Google's video generation model, supports image/video-to-video |

### Video vs Photo Input?

**Verdict: Accept video (prioritize), but also support a single photo as fallback.**

| Input | Pros | Cons |
|-------|------|------|
| **Video (3-5 sec)** | More context (motion, expressions, setting), natural video-to-video continuation, better predictions | Larger upload, longer processing |
| **Photo** | Fast upload, simpler, works as MVP | Less context, still image-to-video is less natural |

The app should record a **short video clip (3-5 seconds)**. This gives Gemini the richest context for scene understanding and gives Veo 2 a natural starting point for video continuation.

---

## How Generated Videos Feel Like a Continuation

The generated scenarios must feel like they're continuing the user's original video, not random unrelated clips. This is achieved by a **two-part handoff** between Gemini and Veo 2:

```
User's Video (3-5 sec)
    │
    ├──── Full video ──▶ Gemini (understands context, people, actions, mood)
    │                         │
    │                         ▼
    │                    4 detailed prompts grounded in the real scene
    │
    └──── Last frame ──▶ Veo 2 (generates video STARTING from this exact image)
                              │
                              ▼
                         4 videos that visually continue from the last frame
```

### Why the last frame matters

Veo 2's image-to-video mode accepts a **reference image** — it generates motion that begins from that exact visual state. By extracting the last frame of the user's video:

- **Same people** — their positions, clothing, and appearance carry over
- **Same environment** — the room, lighting, objects, and background match
- **Same composition** — camera angle and framing are preserved
- **Seamless transition** — the generated video picks up right where the original left off

Without the reference image, Veo 2 would generate from scratch — random people, random room, no visual connection to the original video.

### What each model sees

| Model | Input | Purpose |
|-------|-------|---------|
| **Gemini** | Full video (all frames, audio) | Deeply understand the scene — who's there, what's happening, relationships, mood, objects |
| **Veo 2** | Last frame (image) + text prompt | Generate video that starts from that exact visual and acts out the scenario |

### Continuity trade-offs by scenario type

| Scenario | Visual continuity | Notes |
|----------|-------------------|-------|
| **Positive** (handshake) | High — small natural action | Stays very close to original scene |
| **Bad** (bored judges) | High — subtle expression change | Mostly same composition |
| **Insane** (slap) | Medium — bigger action | Physical movement is larger, but setting stays the same |
| **Funny** (falls off chair) | Medium — physical comedy | More deviation, but still grounded in the original frame |

The prompt engineering step (Step 3) must keep scenarios **physically grounded** in the original scene. Prompts should describe actions involving the actual people/objects visible in the last frame, not introduce entirely new elements.

---

## Core Pipeline (Server-Side)

### Step 1: Receive Video
- iOS app uploads video via `multipart/form-data` to `POST /api/predict`
- Server saves to temp storage (local fs for hackathon, S3/GCS for prod)

### Step 2: Analyze Scene (Gemini 2.5 Flash)
```python
from google import genai
from google.genai import types

client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

response = client.models.generate_content(
    model="gemini-2.5-flash-preview-04-17",
    contents=types.Content(parts=[
        types.Part.from_bytes(data=video_bytes, mime_type="video/mp4"),
        types.Part.from_text("""Analyze this video scene in detail. Describe:
          - Who is in the scene (people, their apparent roles/relationships)
          - What is happening (actions, interactions)
          - The setting/environment
          - The mood/energy
          - Any objects or details that could play into future scenarios"""),
    ]),
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=SceneAnalysis,  # Pydantic model for structured output
    ),
)
```

### Step 3: Generate 4 Scenario Prompts (Gemini 2.5 Flash)
```python
scenarios_response = client.models.generate_content(
    model="gemini-2.5-flash-preview-04-17",
    contents=f"""Scene: {scene_analysis.model_dump_json()}

    Generate exactly 4 scenarios:
    1. POSITIVE — The most likely positive outcome
    2. BAD — A negative/unfortunate outcome
    3. INSANE — A wild, unexpected, over-the-top outcome
    4. FUNNY — A hilarious, comedic outcome

    For each, write a vivid visual description (2-3 sentences) describing
    exactly what happens next. Focus on physical actions, expressions, and
    movements that can be shown in video.""",
    config=types.GenerateContentConfig(
        system_instruction="""You are a creative scenario writer for a
        "predict the future" app. Given a scene analysis, generate 4 possible
        future scenarios that could happen in the NEXT 3-5 seconds. Each
        scenario must be a detailed visual description suitable for video
        generation.""",
        response_mime_type="application/json",
        response_schema=ScenarioPrompts,  # Pydantic model
    ),
)
```

### Step 4: Generate 4 Videos (Veo 2)
```python
import asyncio
from PIL import Image

# Extract last frame from video as reference image
last_frame: Image.Image = extract_last_frame(video_bytes)

async def generate_scenario_video(scenario):
    operation = client.models.generate_videos(
        model="veo-2.0-generate-001",
        prompt=scenario.visual_description,
        image=last_frame,
        config=types.GenerateVideosConfig(
            aspect_ratio="9:16",  # vertical for iPhone
            number_of_videos=1,
        ),
    )
    # Poll until complete
    while not operation.done:
        await asyncio.sleep(5)
        operation = client.operations.get(operation)
    return operation.result

# Generate all 4 videos in parallel
videos = await asyncio.gather(*[
    generate_scenario_video(s) for s in scenarios
])
```

### Step 5: Return Results
```json
{
  "sceneAnalysis": "Two hackathon judges and a friend sitting at a desk...",
  "scenarios": [
    {
      "type": "positive",
      "title": "The Handshake",
      "description": "The judges smile and reach across to shake your friend's hand...",
      "videoUrl": "https://storage.../scenario-1.mp4"
    },
    {
      "type": "bad",
      "title": "The Boredom",
      "description": "The judges' eyes glaze over...",
      "videoUrl": "https://storage.../scenario-2.mp4"
    },
    {
      "type": "insane",
      "title": "The Slap",
      "description": "One judge suddenly stands up and slaps...",
      "videoUrl": "https://storage.../scenario-3.mp4"
    },
    {
      "type": "funny", 
      "title": "The Fall",
      "description": "Your friend leans back too far and...",
      "videoUrl": "https://storage.../scenario-4.mp4"
    }
  ]
}
```

---

## iOS App Flow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Home Screen │────▶│ Camera View  │────▶│  Loading Screen  │────▶│  Results Grid    │
│  "Predict    │     │ Record 3-5s  │     │  "Predicting     │     │  4 scenario      │
│   My Future" │     │ video clip   │     │   your future..."│     │  video cards     │
└──────────────┘     └──────────────┘     └──────────────────┘     └──────────────────┘
                                                                     │ tap a card │
                                                                     ▼            │
                                                                   ┌──────────────┘
                                                                   │ Full-Screen
                                                                   │ Video Player
                                                                   └─────────────
```

### Key iOS Components
- **CameraView**: AVFoundation-based camera with record button, 3-5 sec limit
- **ResultsView**: 2x2 grid of scenario cards, each auto-playing its video
- **ScenarioCardView**: Labeled card (emoji + title + looping video)

---

## Server Dependencies

```
# requirements.txt
fastapi
uvicorn[standard]
google-genai
python-multipart
python-dotenv
pydantic
Pillow
```

| Package | Purpose |
|---------|---------|
| `fastapi` | Web framework — async, auto-docs, type-safe |
| `uvicorn` | ASGI server to run FastAPI |
| `google-genai` | Google's unified SDK for Gemini + Veo 2 |
| `python-multipart` | File upload parsing for FastAPI |
| `python-dotenv` | Load `.env` file for API keys |
| `pydantic` | Data models + structured output schemas |
| `Pillow` | Extract last frame from video for Veo 2 reference image |

---

## API Contract

### `POST /api/predict`

**Request:** `multipart/form-data`
| Field | Type | Description |
|-------|------|-------------|
| `video` | `file` (video/mp4) | 3-5 second video clip |

**Response:** `application/json`
```python
class Scenario(BaseModel):
    type: Literal["positive", "bad", "insane", "funny"]
    title: str
    description: str
    video_url: str

class PredictionResponse(BaseModel):
    id: str
    scene_analysis: str
    scenarios: list[Scenario]
```

---

## Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Veo 2 video generation is slow (30-120s per video) | Bad UX, long wait | Generate all 4 in parallel, show progress, consider showing text descriptions first while videos load |
| Veo 2 API rate limits | Can't generate 4 videos quickly | Queue + retry logic, or fall back to fewer scenarios |
| Video upload size from iPhone | Slow upload on bad wifi | Compress video on-device before upload, limit to 3-5 seconds |
| Generated videos don't match the scene well | Underwhelming results | Strong prompt engineering, include last frame as reference image, iterate on prompts |
| Veo 2 content safety filters | Some "insane" scenarios get blocked | Tone down extreme prompts, have fallback prompts ready |

---

## Hackathon MVP Priorities

### Must Have (Demo Day)
- [ ] iOS: Record short video clip
- [ ] iOS: Upload to server
- [ ] Server: Analyze scene with Gemini
- [ ] Server: Generate 4 scenario prompts
- [ ] Server: Generate 4 videos with Veo 2
- [ ] iOS: Display 4 scenario videos in a grid
- [ ] iOS: Tap to play full-screen

### Nice to Have
- [ ] Loading animations / progress indicators
- [ ] Share a scenario video to social media
- [ ] History of past predictions
- [ ] Photo input fallback
- [ ] On-device video compression

### Future (Post-Hackathon)
- [ ] User accounts
- [ ] Social feed of predictions
- [ ] Custom scenario types
- [ ] Real-time generation with streaming
- [ ] Cloud storage (GCS/S3) for generated videos

---

## Getting Started

### Server
```bash
cd server
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Add your GOOGLE_API_KEY
uvicorn main:app --reload
```

### iOS
```bash
open app/PredictMyFuture.xcodeproj
# Build and run on device (camera requires physical device)
```

---

## Open Questions

1. **Veo 2 access** — Do we have access to the Veo 2 API? Need to check Google AI Studio / Vertex AI availability.
2. **Video length** — Should we cap at 3 seconds or 5 seconds? Shorter = faster upload + processing.
3. **Output aspect ratio** — 9:16 (portrait, matches iPhone recording) or 16:9 (landscape)?
4. **Polling vs SSE** — Should the iOS app poll for results, or should we use Server-Sent Events for real-time progress?
5. **Local dev** — For testing without Veo 2, we could mock the video generation step and return placeholder videos.
