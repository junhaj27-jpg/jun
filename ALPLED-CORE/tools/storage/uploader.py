import shutil
from pathlib import Path
from typing import Any

from config.settings import Settings, get_settings
from tools.result import ToolResult, error_result, success_result
from tools.storage.s3_client import create_s3_client


def upload_file(
    local_file_path: str,
    *,
    storage_path: str | None = None,
    s3_key: str | None = None,
    s3_client: Any | None = None,
    settings: Settings | None = None,
) -> ToolResult:
    config = settings or get_settings()
    try:
        source = Path(local_file_path).resolve(strict=True)
        if storage_path and s3_key:
            return error_result(
                "UPLOAD_TARGET_INVALID",
                "storage_path 또는 s3_key 중 하나만 전달해야 합니다.",
            )
        if s3_key:
            client = s3_client or create_s3_client(config)
            if not config.s3_bucket:
                return error_result("S3_BUCKET_MISSING", "S3_BUCKET이 설정되지 않았습니다.")
            client.upload_file(str(source), config.s3_bucket, s3_key)
            return success_result(
                {
                    "storage_file_path": f"s3://{config.s3_bucket}/{s3_key}",
                    "s3_key": s3_key,
                }
            )

        destination = Path(storage_path or config.output_dir / source.name).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source != destination:
            shutil.copy2(source, destination)
        return success_result({"storage_file_path": str(destination)})
    except Exception as exc:
        return error_result("UPLOAD_FAILED", str(exc))
