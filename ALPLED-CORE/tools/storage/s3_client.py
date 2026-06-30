from typing import Any

from config.settings import Settings, get_settings


def create_s3_client(settings: Settings | None = None) -> Any:
    """Settings 기반 boto3 S3 클라이언트를 생성합니다."""

    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("S3 기능을 사용하려면 boto3가 필요합니다.") from exc

    config = settings or get_settings()
    return boto3.client(
        "s3",
        endpoint_url=config.s3_endpoint or None,
        aws_access_key_id=config.s3_access_key or None,
        aws_secret_access_key=config.s3_secret_key or None,
        region_name=config.s3_region or None,
    )
