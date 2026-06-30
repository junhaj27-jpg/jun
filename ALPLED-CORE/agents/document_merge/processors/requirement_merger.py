# 기존 요구사항과 변경 요구사항 항목을 병합합니다.

from copy import deepcopy
from typing import Any


def merge_items(
    base_items: list[Any],
    change_items: list[dict[str, Any]],
) -> list[Any]:
    merged = deepcopy(base_items)
    for change in change_items:
        change_type = str(change.get("change_type") or change.get("operation") or "UPDATE").upper()
        target_id = change.get("target_id") or change.get("req_id") or change.get("id")
        index = _find_index(merged, target_id)
        content = change.get("item") or change.get("content") or change
        if change_type == "DELETE" and index is not None:
            merged.pop(index)
        elif change_type == "ADD":
            merged.append(content)
        elif index is not None:
            if isinstance(merged[index], dict) and isinstance(content, dict):
                merged[index] = {**merged[index], **content}
            else:
                merged[index] = content
        elif change_type == "UPDATE" and target_id is not None:
            merged.append(content)
    return merged


def _find_index(items: list[Any], target_id: Any) -> int | None:
    if target_id is None:
        return None
    target = str(target_id)
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        values = (
            item.get("req_id"),
            item.get("requirement_id"),
            item.get("gold_id"),
            item.get("id"),
            item.get("artifact_id"),
            item.get("screen_id"),
        )
        if any(str(value) == target for value in values if value is not None):
            return index
    return None
