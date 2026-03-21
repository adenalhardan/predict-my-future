from __future__ import annotations

import os
from datetime import timedelta

from google.cloud import storage
from google.oauth2 import service_account

_storage_client = None
GCS_PREFIX = "predict-future"


def _get_bucket_name() -> str | None:
    return os.getenv("GCS_BUCKET")


def _prefixed(blob_path: str) -> str:
    return f"{GCS_PREFIX}/{blob_path}"


def _get_storage_client() -> storage.Client:
    """Build a storage client using service-account env vars when available,
    otherwise fall back to Application Default Credentials."""
    global _storage_client
    if _storage_client is not None:
        return _storage_client

    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    private_key = os.getenv("GCS_PRIVATE_KEY")
    client_email = os.getenv("GCS_CLIENT_EMAIL")

    if private_key and client_email:
        creds = service_account.Credentials.from_service_account_info({
            "type": "service_account",
            "project_id": project,
            "private_key": private_key.replace("\\n", "\n"),
            "client_email": client_email,
            "token_uri": "https://oauth2.googleapis.com/token",
        })
        _storage_client = storage.Client(project=project, credentials=creds)
    else:
        _storage_client = storage.Client(project=project)

    return _storage_client


def generate_upload_signed_url(blob_path: str, content_type: str = "video/mp4") -> str:
    """Create a V4 signed URL that lets the client PUT a file directly to GCS."""
    bucket_name = _get_bucket_name()
    client = _get_storage_client()
    full_path = _prefixed(blob_path)
    blob = client.bucket(bucket_name).blob(full_path)
    return blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=15),
        method="PUT",
        content_type=content_type,
    )


def generate_download_signed_url(blob_path: str, expiry_minutes: int = 60) -> str:
    """Create a V4 signed URL that lets the client GET a file from GCS."""
    bucket_name = _get_bucket_name()
    client = _get_storage_client()
    full_path = _prefixed(blob_path)
    blob = client.bucket(bucket_name).blob(full_path)
    return blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=expiry_minutes),
        method="GET",
    )


def upload_bytes_to_gcs(blob_path: str, data: bytes, content_type: str = "video/mp4"):
    """Upload raw bytes to a GCS blob."""
    bucket_name = _get_bucket_name()
    client = _get_storage_client()
    full_path = _prefixed(blob_path)
    blob = client.bucket(bucket_name).blob(full_path)
    blob.upload_from_string(data, content_type=content_type)
    print(f"[GCS] Uploaded {len(data)} bytes to gs://{bucket_name}/{full_path}")


def download_bytes_from_gcs(blob_path: str) -> bytes:
    """Download a blob from GCS and return its contents."""
    bucket_name = _get_bucket_name()
    client = _get_storage_client()
    full_path = _prefixed(blob_path)
    blob = client.bucket(bucket_name).blob(full_path)
    data = blob.download_as_bytes()
    print(f"[GCS] Downloaded {len(data)} bytes from gs://{bucket_name}/{full_path}")
    return data


def is_gcs_enabled() -> bool:
    return bool(_get_bucket_name())
