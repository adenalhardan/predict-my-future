import os

from google.cloud import storage

BUCKET_NAME = "seecircle-cdn"
PROJECT_ID = os.environ["GCP_PROJECT_ID"]
CLIENT_EMAIL = os.environ["GCP_CLIENT_EMAIL"]
PRIVATE_KEY = os.environ["GCP_PRIVATE_KEY"].replace("\\n", "\n")


def get_storage_client() -> storage.Client:
    credentials_info = {
        "type": "service_account",
        "project_id": PROJECT_ID,
        "private_key": PRIVATE_KEY,
        "client_email": CLIENT_EMAIL,
        "token_uri": "https://oauth2.googleapis.com/token",
    }

    credentials = service_account.Credentials.from_service_account_info(
        credentials_info
    )

    return storage.Client(project=PROJECT_ID, credentials=credentials)
