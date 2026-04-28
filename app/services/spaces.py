# app/services/spaces.py
# DigitalOcean Spaces file upload service.
# Uses boto3 pointed at the DO endpoint — fully S3-compatible.
# Called by the photo and banner upload endpoints in candidates.py.

import logging
import mimetypes
import uuid

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_client():
    return boto3.client(
        "s3",
        region_name=settings.DO_SPACES_REGION,
        endpoint_url=settings.DO_SPACES_ENDPOINT,
        aws_access_key_id=settings.DO_SPACES_KEY,
        aws_secret_access_key=settings.DO_SPACES_SECRET,
    )


def upload_file(
    file_bytes: bytes,
    folder: str,
    filename: str,
    content_type: str | None = None,
) -> str | None:
    """
    Upload file_bytes to DO Spaces under folder/filename.
    Returns the public CDN URL on success, None on failure.

    Example:
        url = upload_file(data, "candidates/42/photo", "photo.jpg", "image/jpeg")
        # → "https://ryzerecruiting.nyc3.cdn.digitaloceanspaces.com/candidates/42/photo/photo.jpg"
    """
    if not settings.DO_SPACES_KEY or not settings.DO_SPACES_BUCKET:
        logger.error("[spaces] DO Spaces not configured — missing key or bucket")
        return None

    key = f"{folder}/{filename}"

    # Guess content type from filename if not provided
    if not content_type:
        content_type, _ = mimetypes.guess_type(filename)
        content_type = content_type or "application/octet-stream"

    try:
        client = _get_client()
        client.put_object(
            Bucket=settings.DO_SPACES_BUCKET,
            Key=key,
            Body=file_bytes,
            ContentType=content_type,
            ACL="public-read",
        )
        cdn_url = f"{settings.DO_SPACES_CDN_BASE.rstrip('/')}/{key}"
        logger.info(f"[spaces] Uploaded {key} → {cdn_url}")
        return cdn_url

    except (BotoCoreError, ClientError) as e:
        logger.error(f"[spaces] Upload failed for {key}: {e}")
        return None


def delete_file(key: str) -> bool:
    """
    Delete a file from DO Spaces by its key (path within the bucket).
    Returns True on success, False on failure.
    """
    if not settings.DO_SPACES_KEY or not settings.DO_SPACES_BUCKET:
        return False
    try:
        client = _get_client()
        client.delete_object(Bucket=settings.DO_SPACES_BUCKET, Key=key)
        logger.info(f"[spaces] Deleted {key}")
        return True
    except (BotoCoreError, ClientError) as e:
        logger.error(f"[spaces] Delete failed for {key}: {e}")
        return False


def make_unique_filename(original_filename: str) -> str:
    """
    Generates a unique filename preserving the original extension.
    Prevents cache collisions when replacing a photo.
    e.g. "headshot.jpg" → "a3f2c1d4.jpg"
    """
    ext = (
        original_filename.rsplit(".", 1)[-1].lower()
        if "." in original_filename
        else "bin"
    )
    return f"{uuid.uuid4().hex}.{ext}"
