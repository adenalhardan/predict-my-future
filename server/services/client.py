import os
from google import genai

_client = None


def get_client() -> genai.Client:
    """Shared Google GenAI client singleton used by all services.

    Uses API key auth if GOOGLE_API_KEY is set,
    otherwise falls back to Vertex AI with project/location + ADC.
    """
    global _client
    if _client is None:
        api_key = os.getenv("GOOGLE_API_KEY")
        if api_key:
            _client = genai.Client(api_key=api_key)
        else:
            _client = genai.Client(
                vertexai=True,
                project=os.getenv("GOOGLE_CLOUD_PROJECT"),
                location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
            )
    return _client
