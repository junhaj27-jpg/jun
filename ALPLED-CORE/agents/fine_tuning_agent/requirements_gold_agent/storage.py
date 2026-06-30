from __future__ import annotations

import csv
import errno
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

from .config import JSON_WRITE_RETRY_COUNT, JSON_WRITE_RETRY_SECONDS


def dump_json(path: Path, obj: Any) -> Path:
    """임시 파일 기록 후 os.replace로 원자 교체하며 일시적 저장 오류를 재시도한다."""
    path = Path(path)
    try:
        serialized = json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception as exc:
        raise RuntimeError(f"JSON 직렬화 실패: {path}") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    last_error: OSError | None = None
    retryable = {errno.EIO, errno.ENOSPC, errno.ESTALE, errno.EBUSY}
    for attempt in range(1, JSON_WRITE_RETRY_COUNT + 1):
        temp_path = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as file:
                file.write(serialized)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp_path, path)
            if not path.exists() or path.stat().st_size <= 0:
                raise OSError(errno.EIO, "저장 후 파일이 없거나 크기가 0임")
            return path
        except OSError as exc:
            last_error = exc
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
            if attempt >= JSON_WRITE_RETRY_COUNT or exc.errno not in retryable:
                break
            time.sleep(JSON_WRITE_RETRY_SECONDS * attempt)
    raise OSError(getattr(last_error, "errno", errno.EIO), f"JSON 저장 반복 실패: {path}; last={last_error}")


def load_json(path: Path) -> Any:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: Iterable[dict]) -> Path:
    rows = list(rows)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        if fieldnames:
            writer.writeheader()
            writer.writerows(rows)
    return path
