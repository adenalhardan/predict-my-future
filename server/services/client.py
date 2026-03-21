import os
from google import genai

_client = None


def get_client() -> genai.Client:
    """Shared Vertex AI client singleton used by all services."""
    global _client
    if _client is None:
        _client = genai.Client(
            vertexai=True,
            project=os.getenv("GOOGLE_CLOUD_PROJECT"),
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
            api_key=os.getenv("GOOGLE_API_KEY"),
        )
    return _client
