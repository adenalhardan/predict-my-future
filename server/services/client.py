import os
from google import genai
from google.oauth2 import service_account

_client = None
_veo_client = None


def get_client() -> genai.Client:
    """Shared Google GenAI client for text models (Gemini).

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


def _build_vertex_credentials() -> service_account.Credentials | None:
    """Build service account credentials from GCS_PRIVATE_KEY / GCS_CLIENT_EMAIL."""
    private_key = os.getenv("GCS_PRIVATE_KEY")
    client_email = os.getenv("GCS_CLIENT_EMAIL")
    project = os.getenv("GOOGLE_CLOUD_PROJECT")

    if private_key and client_email:
        creds = service_account.Credentials.from_service_account_info(
            {
                "type": "service_account",
                "project_id": project,
                "private_key": private_key.replace("\\n", "\n"),
                "client_email": client_email,
                "token_uri": "https://oauth2.googleapis.com/token",
            },
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        return creds
    return None


def get_veo_client() -> genai.Client:
    """Vertex AI client for Veo video generation.

    Uses separate Vertex AI quota (50 RPM) instead of Gemini API quota (2 RPM).
    Authenticates with service account credentials when available, falls back to ADC.
    """
    global _veo_client
    if _veo_client is None:
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        creds = _build_vertex_credentials()

        _veo_client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
            credentials=creds,
        )
    return _veo_client
