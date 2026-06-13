import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from config.settings import Settings, get_settings
from tools.result import ToolResult, error_result, success_result
from tools.storage.s3_client import create_s3_client


def download_file(
    *,
    file_path: str | None = None,
    s3_key: str | None = None,
    file_name: str | None = None,
    destination_dir: str | Path | None = None,
    s3_client: Any | None = None,
    settings: Settings | None = None,
) -> ToolResult:
    """Repository가 조회한 file_path 또는 s3_key를 로컬로 다운로드합니다."""

    config = settings or get_settings()
    destination = Path(destination_dir or config.input_dir).resolve()
    try:
        if bool(file_path) == bool(s3_key):
            return error_result(
                "DOWNLOAD_SOURCE_INVALID",
                "file_path 또는 s3_key 중 하나만 전달해야 합니다.",
            )

        destination.mkdir(parents=True, exist_ok=True)
        source = file_path or s3_key or ""
        resolved_name = file_name or Path(urlparse(source).path).name
        if not resolved_name:
            return error_result("DOWNLOAD_FILE_NAME_MISSING", "저장할 파일명을 확인할 수 없습니다.")
        target = destination / Path(resolved_name).name

        if s3_key:
            client = s3_client or create_s3_client(config)
            if not config.s3_bucket:
                return error_result("S3_BUCKET_MISSING", "S3_BUCKET이 설정되지 않았습니다.")
            client.download_file(config.s3_bucket, s3_key, str(target))
        elif file_path and file_path.startswith(("http://", "https://")):
            _download_http(file_path, target)
        else:
            shutil.copy2(Path(file_path or "").resolve(strict=True), target)
        return success_result(
            {
                "local_file_path": str(target),
                "source": {"file_path": file_path, "s3_key": s3_key},
            }
        )
    except Exception as exc:
        return error_result("DOWNLOAD_FAILED", str(exc))


def _download_http(source: str, target: Path) -> None:
    with requests.get(source, stream=True, timeout=60) as response:
        response.raise_for_status()
        with open(target, "wb") as output:
            shutil.copyfileobj(response.raw, output)
