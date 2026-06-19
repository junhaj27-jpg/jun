from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable


def dedupe_preserve(values: Iterable[Any] | Any | None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        token = str(value).strip()
        if token and token not in seen:
            seen.add(token)
            result.append(token)
    return result


def canonical_json_sha256(obj: Any) -> str:
    payload = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def text_sha256(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def safe_file_component(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", str(value).strip()).strip("._")
    return cleaned or hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:16]
