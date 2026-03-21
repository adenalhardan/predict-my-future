from google.genai import types
from models.schemas import SceneAnalysis, ScenarioPrompts
from services.client import get_client


MODEL = "gemini-2.5-flash"

SYSTEM_INSTRUCTION = (
    "You are a creative scenario writer for a 'predict the future' app. "
    "Given a scene analysis, generate 4 possible future scenarios that could "
    "happen in the NEXT 3-5 seconds. Each scenario must be a detailed visual "
    "description suitable for video generation. Keep all scenarios physically "
    "grounded in the original scene — same people, same location, same objects. "
    "The INSANE scenario is the exception: it CAN introduce a famous person or "
    "surreal element that was NOT in the original scene.\n\n"
    "IMPORTANT SAFETY GUIDELINES for visual_description:\n"
    "- Never describe violence, harm, threats, or aggressive physical contact.\n"
    "- 'Bad' scenarios should be awkward, embarrassing, or unfortunate — NOT violent.\n"
    "- 'Insane' scenarios should be surreal or absurd — NOT dangerous.\n"
    "- Keep all scenarios family-friendly and suitable for AI video generation.\n\n"
    "EXAMPLE — Input scene: A guy is standing up explaining something to 3 other "
    "people who are sitting in an open workspace.\n"
    "Expected output:\n"
    "{\n"
    '  "scenarios": [\n'
    "    {\n"
    '      "type": "positive",\n'
    '      "title": "Standing Ovation",\n'
    '      "description": "72% chance — The three seated people break into enthusiastic '
    'applause, smiling and nodding at the presenter.",\n'
    '      "visual_description": "The three seated listeners simultaneously begin '
    "clapping their hands with big smiles on their faces. The standing presenter "
    "beams with pride, gesturing appreciatively. The energy in the room shifts to "
    'celebration as everyone leans forward with excitement."\n'
    "    },\n"
    "    {\n"
    '      "type": "bad",\n'
    '      "title": "Total Walkout",\n'
    '      "description": "15% chance — The seated group loses interest and gets up '
    'to leave mid-explanation.",\n'
    '      "visual_description": "One by one, the three seated people stand up from '
    "their chairs, grab their laptops and bags, and walk away from the presenter. "
    "The standing man is left alone mid-sentence with his hand still raised, looking "
    'confused and deflated."\n'
    "    },\n"
    "    {\n"
    '      "type": "insane",\n'
    '      "title": "Trump Crashes Meeting",\n'
    '      "description": "0.1% chance — Donald Trump unexpectedly walks into the '
    'meeting and everyone is shocked.",\n'
    '      "visual_description": "Donald Trump in a suit and red tie strides '
    "confidently into the workspace from the background. The seated people's jaws "
    "drop in disbelief, turning around in their chairs. The presenter freezes "
    'mid-gesture, staring wide-eyed as Trump gives a thumbs up."\n'
    "    },\n"
    "    {\n"
    '      "type": "funny",\n'
    '      "title": "Surprise Twerk",\n'
    '      "description": "5% chance — The presenter suddenly stops explaining and '
    'breaks into a twerk.",\n'
    '      "visual_description": "The standing presenter abruptly stops talking, '
    "turns around, and starts twerking energetically. The three seated people burst "
    "out laughing, one nearly falling off their chair. The presenter keeps going with "
    'full commitment, shaking to an invisible beat."\n'
    "    }\n"
    "  ]\n"
    "}"
)


async def generate_prompts(scene: SceneAnalysis) -> ScenarioPrompts:
    """Generate 4 scenario prompts from a scene analysis."""
    client = get_client()
    response = await client.aio.models.generate_content(
        model=MODEL,
        contents=(
            f"Scene analysis:\n{scene.model_dump_json(indent=2)}\n\n"
            "Generate exactly 4 scenarios following the example in the system "
            "instructions. The 4 output types are:\n"
            "1. POSITIVE (type='positive') — The most likely positive outcome\n"
            "2. BAD (type='bad') — A negative or unfortunate outcome\n"
            "3. INSANE (type='insane') — A wild, unexpected, over-the-top outcome "
            "(CAN introduce a famous person or surreal element)\n"
            "4. FUNNY (type='funny') — A hilarious, comedic outcome\n\n"
            "For each scenario provide:\n"
            "- type: one of 'positive', 'bad', 'insane', 'funny'\n"
            "- title: a short catchy title (2-4 words)\n"
            "- description: start with a realistic probability estimate "
            "(e.g. '72% chance —', '3% chance —'), then a short sentence describing "
            "what happens. Keep the tone fun and punchy.\n"
            "- visual_description: 2-3 sentences of vivid visual detail describing "
            "exactly what happens next, focusing on physical actions, expressions, "
            "and movements that can be shown in video. This is fed directly to a "
            "video generation model so be specific and cinematic."
        ),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=ScenarioPrompts,
        ),
    )
    return ScenarioPrompts.model_validate_json(response.text)
