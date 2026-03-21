from google.genai import types
from models.schemas import SceneAnalysis
from services.client import get_client


MODEL = "gemini-2.5-flash"


async def analyze_scene(video_bytes: bytes, mime_type: str = "video/mp4") -> SceneAnalysis:
    """Send video to Gemini and get a structured scene analysis."""
    client = get_client()
    response = await client.aio.models.generate_content(
        model=MODEL,
        contents=types.Content(parts=[
            types.Part.from_bytes(data=video_bytes, mime_type=mime_type),
            types.Part(text=(
                "Analyze this video scene in detail. Describe:\n"
                "- people: Who is in the scene (appearance, apparent roles/relationships)\n"
                "- actions: What is happening (actions, interactions, body language)\n"
                "- setting: The environment (indoor/outdoor, location type, notable features)\n"
                "- mood: The overall energy and emotional tone\n"
                "- key_objects: Important objects or details that could play into future scenarios"
            )),
        ]),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SceneAnalysis,
        ),
    )
    return SceneAnalysis.model_validate_json(response.text)
