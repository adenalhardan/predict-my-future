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
    "The INSANE scenario is the exception: it CAN introduce surreal, "
    "physics-defying, or magical elements — but NEVER real famous people or "
    "celebrities. Think: gravity reverses, objects come alive, clones appear, "
    "portals open, things shrink/grow, etc.\n\n"
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
    '      "title": "Zero Gravity",\n'
    '      "description": "0.1% chance — Gravity suddenly switches off and everyone '
    'starts floating.",\n'
    '      "visual_description": "Mid-sentence, the presenter\'s feet lift off the '
    "ground. The seated people rise out of their chairs, laptops and bags floating "
    "around them. Everyone grabs at the air in panic, drifting slowly upward with "
    'wide eyes and flailing limbs."\n'
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
    "}\n\n"
    "EXAMPLE 2 — Input scene: A guy is standing alone on the street talking on his phone.\n"
    "Expected output:\n"
    "{\n"
    '  "scenarios": [\n'
    "    {\n"
    '      "type": "positive",\n'
    '      "title": "Great News",\n'
    '      "description": "55% chance — He receives amazing news and jumps for joy.",\n'
    '      "visual_description": "The man\'s eyes widen as he hears something on the phone. '
    "A huge grin spreads across his face and he leaps into the air with both fists raised, "
    'phone still in hand. He lands and pumps his fist, practically bouncing with excitement."\n'
    "    },\n"
    "    {\n"
    '      "type": "bad",\n'
    '      "title": "Devastating Call",\n'
    '      "description": "20% chance — He gets terrible news and breaks down crying.",\n'
    '      "visual_description": "The man\'s expression crumbles as he listens to the phone. '
    "He slowly lowers the phone from his ear, his shoulders slumping. He covers his face "
    'with his free hand as tears stream down his cheeks, visibly shaking."\n'
    "    },\n"
    "    {\n"
    '      "type": "insane",\n'
    '      "title": "Liftoff",\n'
    '      "description": "0.01% chance — He suddenly starts levitating off the ground.",\n'
    '      "visual_description": "Mid-conversation, the man\'s feet slowly lift off the '
    "pavement. He rises a few feet into the air, still holding the phone to his ear, "
    "looking down in total shock. His legs dangle as he floats upward, arms flailing "
    'for balance."\n'
    "    },\n"
    "    {\n"
    '      "type": "funny",\n'
    '      "title": "Spontaneous Dance",\n'
    '      "description": "8% chance — He suddenly breaks into a full dance routine '
    'on the sidewalk.",\n'
    '      "visual_description": "The man pockets his phone and suddenly busts into '
    "a funky dance, sliding his feet and rolling his arms. Passersby stare in confusion "
    "as he hits increasingly dramatic moves, spinning and pointing at strangers with "
    'finger guns."\n'
    "    }\n"
    "  ]\n"
    "}\n\n"
    "EXAMPLE 3 — Input scene: Two people sitting across from each other at a table, "
    "both with laptops open in front of them.\n"
    "Expected output:\n"
    "{\n"
    '  "scenarios": [\n'
    "    {\n"
    '      "type": "positive",\n'
    '      "title": "Deal Sealed",\n'
    '      "description": "80% chance — They reach an agreement and shake hands '
    'across the table.",\n'
    '      "visual_description": "Both people smile and close their laptops '
    "simultaneously. They stand up slightly and reach across the table for a firm, "
    "enthusiastic handshake. They nod at each other approvingly, clearly pleased "
    'with the outcome of their discussion."\n'
    "    },\n"
    "    {\n"
    '      "type": "bad",\n'
    '      "title": "Laptop Smash",\n'
    '      "description": "12% chance — One of them accidentally knocks the other\'s '
    'laptop off the table.",\n'
    '      "visual_description": "One person gestures too broadly and their arm sweeps '
    "across the table, slamming into the other person's open laptop. The laptop slides "
    "off the edge and crashes to the floor screen-first. The owner stares down in horror "
    'while the other person freezes with their hand still mid-air, mouth open."\n'
    "    },\n"
    "    {\n"
    '      "type": "insane",\n'
    '      "title": "Zero Gravity",\n'
    '      "description": "0.01% chance — Gravity shuts off and everything on the table '
    'starts floating.",\n'
    '      "visual_description": "Both laptops slowly lift off the table and drift '
    "upward. Pens, notebooks, and coffee cups follow, floating in mid-air. The two "
    "people grip the table edges in shock as their chairs begin to rise, legs dangling "
    'as everything in the room drifts weightlessly."\n'
    "    },\n"
    "    {\n"
    '      "type": "funny",\n'
    '      "title": "Victory Dance",\n'
    '      "description": "7.99% chance — One of them suddenly stands up and breaks into '
    'a celebratory dance.",\n'
    '      "visual_description": "One person abruptly pushes their chair back and leaps '
    "to their feet, arms raised in triumph. They launch into an exaggerated dance, "
    "shimmying their shoulders and doing a spin. The other person leans back in their "
    'chair, laughing uncontrollably and clapping along."\n'
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
            "3. INSANE (type='insane') — A wild, surreal, physics-defying outcome "
            "(NO real celebrities — use magical/surreal elements instead)\n"
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
