"""Upload generated images to S3 (photome-ai-bucket)."""
import boto3
from decouple import config

S3_BUCKET = config("S3_BUCKET", default="photome-ai-bucket")
S3_REGION = config("S3_REGION", default="us-east-1")
S3_PREFIX = config("S3_PREFIX", default="data")


def get_s3_client():
    """Build S3 client from env: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY."""
    return boto3.client(
        "s3",
        region_name=S3_REGION,
        aws_access_key_id=config("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=config("AWS_SECRET_ACCESS_KEY"),
    )


def upload_bytes(
    body: bytes,
    key: str,
    content_type: str = "image/jpeg",
    bucket: str | None = None,
) -> str:
    """
    Upload raw bytes to S3 and return the public object URL.
    key: object key under bucket (e.g. data/{prediction_id}/0.jpg).
    """
    bucket = bucket or S3_BUCKET
    client = get_s3_client()
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType=content_type,
    )
    return f"https://{bucket}.s3.{S3_REGION}.amazonaws.com/{key}"


def get_presigned_url(key: str, expires_in: int = 3600) -> str:
    """Generate a temporary presigned GET URL so the frontend can load private S3 objects."""
    client = get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET, "Key": key},
        ExpiresIn=expires_in,
    )


def get_presigned_urls_for_prediction(prediction_id: str, num_outputs: int, ext: str = ".jpg") -> list[str] | None:
    """
    If objects for this prediction already exist in S3, return presigned URLs for them.
    Otherwise return None (caller should upload first).
    """
    client = get_s3_client()
    prefix = f"{S3_PREFIX}/{prediction_id}/"
    try:
        paginator = client.get_paginator("list_objects_v2")
        keys = []
        for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
            for obj in page.get("Contents") or []:
                keys.append(obj["Key"])
        if not keys:
            return None
        keys.sort()
        if len(keys) < num_outputs:
            return None
        return [get_presigned_url(k) for k in keys[:num_outputs]]
    except Exception:
        return None


def upload_prediction_outputs(prediction_id: str, files: list[tuple[int, bytes, str]]) -> list[str]:
    """
    Upload multiple output files for a prediction.
    files: list of (index, content_bytes, extension e.g. '.jpg').
    Returns list of presigned URLs (valid 1 hour) so the frontend can display images without public bucket.
    """
    content_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    client = get_s3_client()
    prefix = f"{S3_PREFIX}/{prediction_id}"
    keys_uploaded = []
    for index, content, ext in files:
        key = f"{prefix}/{index}{ext}"
        content_type = content_types.get(ext.lower(), "application/octet-stream")
        client.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
        keys_uploaded.append(key)
    return [get_presigned_url(key) for key in keys_uploaded]
