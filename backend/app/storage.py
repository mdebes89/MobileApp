import logging

import boto3
from botocore.client import Config

from app.config import get_settings

log = logging.getLogger(__name__)
_client = None


def s3_client():
    global _client
    if _client is None:
        settings = get_settings()
        _client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            region_name=settings.aws_region,
            aws_access_key_id=settings.s3_access_key_id or None,
            aws_secret_access_key=settings.s3_secret_access_key or None,
            config=Config(signature_version="s3v4"),
        )
    return _client


def upload_bytes(object_key: str, data: bytes, content_type: str) -> str:
    settings = get_settings()
    s3_client().put_object(Bucket=settings.s3_bucket, Key=object_key, Body=data, ContentType=content_type)
    return object_key


def presign_get(object_key: str, expires: int | None = None) -> str:
    settings = get_settings()
    return s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": object_key},
        ExpiresIn=expires or settings.s3_presign_expiry_seconds,
    )


def object_exists(object_key: str) -> bool:
    settings = get_settings()
    try:
        s3_client().head_object(Bucket=settings.s3_bucket, Key=object_key)
        return True
    except Exception:
        return False
