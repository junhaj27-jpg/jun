import json
import os
from typing import Any


# MAX_ITEMS_PER_CHUNK = int(os.getenv("SRS_CHUNK_MAX_ITEMS", "1"))
# MAX_CHARS_PER_CHUNK = int(os.getenv("SRS_CHUNK_MAX_CHARS", "2500"))
# MAX_FIELD_CHARS = int(os.getenv("SRS_FIELD_MAX_CHARS", "500"))
# MAX_CONTEXT_CHARS = int(os.getenv("SRS_CONTEXT_MAX_CHARS", "800"))

# 14B
MAX_ITEMS_PER_CHUNK = int(os.getenv("SRS_CHUNK_MAX_ITEMS", "3"))
MAX_CHARS_PER_CHUNK = int(os.getenv("SRS_CHUNK_MAX_CHARS", "7000"))
MAX_FIELD_CHARS = int(os.getenv("SRS_FIELD_MAX_CHARS", "2000"))
MAX_CONTEXT_CHARS = int(os.getenv("SRS_CONTEXT_MAX_CHARS", "4000"))


_DROP_KEYS = {
    "raw_text",
    "full_text",
    "page_text",
    "chunks",
    "tables",
    "pages",
    "embedding",
    "vector",
}


def compact_text(value: Any, max_chars: int = MAX_CONTEXT_CHARS) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n...(길이 제한으로 일부 생략)"


def compact_value(value: Any, max_chars: int = MAX_FIELD_CHARS) -> Any:
    if isinstance(value, str):
        return compact_text(value, max_chars)
    if isinstance(value, list):
        compacted = []
        current_chars = 0
        for item in value:
            compacted_item = compact_value(item, max_chars)
            item_chars = len(json.dumps(compacted_item, ensure_ascii=False))
            if compacted and current_chars + item_chars > max_chars:
                compacted.append("...(길이 제한으로 나머지 항목 생략)")
                break
            compacted.append(compacted_item)
            current_chars += item_chars
        return compacted
    if isinstance(value, dict):
        return {
            key: compact_value(item, max_chars)
            for key, item in value.items()
            if key not in _DROP_KEYS
        }
    return value


def compact_item(item: dict[str, Any]) -> dict[str, Any]:
    preferred_keys = [
        "requirement_id",
        "requirement_name",
        "requirement_type",
        "description",
        "source",
        "constraints",
        "priority",
        "validation_criteria",
        "note",
    ]
    compacted = {
        key: compact_value(item.get(key))
        for key in preferred_keys
        if key in item
    }
    if compacted:
        return compacted
    return compact_value(item)


def chunk_items(items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0

    for item in items:
        compacted = compact_item(item)
        item_chars = len(json.dumps(compacted, ensure_ascii=False))

        if current and (
            len(current) >= MAX_ITEMS_PER_CHUNK
            or current_chars + item_chars > MAX_CHARS_PER_CHUNK
        ):
            chunks.append(current)
            current = []
            current_chars = 0

        current.append(compacted)
        current_chars += item_chars

    if current:
        chunks.append(current)

    return chunks
