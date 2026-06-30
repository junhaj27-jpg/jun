import os
import time
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def uses_s3_storage():
    return getattr(settings, "ALPLED_STORAGE_BACKEND", "filesystem") == "s3"


def _get_default_bucket():
    bucket_name = str(getattr(settings, "AWS_STORAGE_BUCKET_NAME", "") or "").strip()
    if not bucket_name:
        raise ImproperlyConfigured("AWS_STORAGE_BUCKET_NAME is required for S3 file paths.")
    return bucket_name


def _normalize_key(key):
    return str(key or "").replace("\\", "/").lstrip("/")


def _get_local_root():
    root = Path(getattr(settings, "ALPLED_LOCAL_STORAGE_ROOT"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _get_local_path(key):
    normalized_key = _normalize_key(key)
    path = _get_local_root() / normalized_key
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _get_s3_client():
    try:
        import boto3
    except ModuleNotFoundError as exc:
        raise ImproperlyConfigured("boto3 is required when S3 storage is enabled.") from exc

    client_kwargs = {
        "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
        "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
        "region_name": settings.AWS_S3_REGION_NAME,
    }
    if settings.AWS_S3_ENDPOINT_URL:
        client_kwargs["endpoint_url"] = settings.AWS_S3_ENDPOINT_URL
    return boto3.client("s3", **client_kwargs)


def build_s3_uri(key, bucket=None):
    normalized_key = _normalize_key(key)
    if not normalized_key:
        raise ValueError("Storage key is required.")
    bucket_name = str(bucket or _get_default_bucket()).strip()
    return f"s3://{bucket_name}/{normalized_key}"


def parse_s3_uri(uri):
    value = str(uri or "").strip()
    prefix = "s3://"
    if not value.startswith(prefix):
        raise ValueError("Expected file_path to contain an S3 URI.")

    bucket_and_key = value[len(prefix):]
    bucket_name, separator, key = bucket_and_key.partition("/")
    normalized_key = _normalize_key(key)
    if not bucket_name or separator != "/" or not normalized_key:
        raise ValueError("Expected file_path to contain an S3 URI.")
    return bucket_name, normalized_key


def save_bytes(key, content, content_type=None, bucket=None):
    normalized_key = _normalize_key(key)
    payload = content or b""

    if uses_s3_storage():
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type
        _get_s3_client().put_object(
            Bucket=str(bucket or _get_default_bucket()).strip(),
            Key=normalized_key,
            Body=payload,
            **extra_args,
        )
        return normalized_key

    path = _get_local_path(normalized_key)
    path.write_bytes(payload)
    return normalized_key


def read_bytes(key, bucket=None):
    normalized_key = _normalize_key(key)
    if not normalized_key:
        return b""

    if uses_s3_storage():
        response = _get_s3_client().get_object(
            Bucket=str(bucket or _get_default_bucket()).strip(),
            Key=normalized_key,
        )
        return response["Body"].read()

    path = _get_local_path(normalized_key)
    return path.read_bytes() if path.exists() else b""


def read_bytes_from_uri(uri):
    bucket_name, key = parse_s3_uri(uri)
    return read_bytes(key, bucket=bucket_name)


def delete_object(key, bucket=None):
    normalized_key = _normalize_key(key)
    if not normalized_key:
        return

    if uses_s3_storage():
        _get_s3_client().delete_object(
            Bucket=str(bucket or _get_default_bucket()).strip(),
            Key=normalized_key,
        )
        return

    path = _get_local_path(normalized_key)
    for _ in range(3):
        try:
            path.unlink(missing_ok=True)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            try:
                os.chmod(path, 0o666)
            except OSError:
                pass
            time.sleep(0.05)
        except OSError:
            return


def delete_object_at_uri(uri):
    bucket_name, key = parse_s3_uri(uri)
    delete_object(key, bucket=bucket_name)


def object_exists(key, bucket=None):
    normalized_key = _normalize_key(key)
    if not normalized_key:
        return False

    if uses_s3_storage():
        try:
            _get_s3_client().head_object(
                Bucket=str(bucket or _get_default_bucket()).strip(),
                Key=normalized_key,
            )
            return True
        except Exception:
            return False

    return _get_local_path(normalized_key).exists()


def object_exists_at_uri(uri):
    bucket_name, key = parse_s3_uri(uri)
    return object_exists(key, bucket=bucket_name)
