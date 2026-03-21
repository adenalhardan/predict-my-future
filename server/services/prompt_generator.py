from google.genai import types
from models.schemas import SceneAnalysis, ScenarioPrompts
from services.client import get_client


MODEL = "gemini-2.5-flash-preview-04-17"

SYSTEM_INSTRUCTION = (
    "You are a creative scenario writer for a 'predict the future' app. "
    "Given a scene analysis, generate 4 possible future scenarios that could "
    "happen in the NEXT 3-5 seconds. Each scenario must be a detailed visual "
    "description suitable for video generation. Keep all scenarios physically "
    "grounded in the original scene — same people, same location, same objects. "
    "Do NOT introduce new characters or locations."
)


async def generate_prompts(scene: SceneAnalysis) -> ScenarioPrompts:
    """Generate 4 scenario prompts from a scene analysis."""
    client = get_client()
    response = await client.aio.models.generate_content(
        model=MODEL,
        contents=(
            f"Scene analysis:\n{scene.model_dump_json(indent=2)}\n\n"
            "Generate exactly 4 scenarios:\n"
            "1. POSITIVE (type='positive') — The most likely positive outcome\n"
            "2. BAD (type='bad') — A negative or unfortunate outcome\n"
            "3. INSANE (type='insane') — A wild, unexpected, over-the-top outcome\n"
            "4. FUNNY (type='funny') — A hilarious, comedic outcome\n\n"
            "For each scenario provide:\n"
            "- type: one of 'positive', 'bad', 'insane', 'funny'\n"
            "- title: a short catchy title (2-4 words)\n"
            "- description: one sentence summary for the user\n"
            "- visual_description: 2-3 sentences of vivid visual detail describing "
            "exactly what happens next, focusing on physical actions, expressions, "
            "and movements that can be shown in video"
        ),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=ScenarioPrompts,
        ),
    )
    return ScenarioPrompts.model_validate_json(response.text)
