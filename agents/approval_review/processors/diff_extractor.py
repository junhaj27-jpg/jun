from __future__ import annotations

from typing import Any


IDENTITY_KEYS = (
    "requirement_id",
    "entity_id",
    "table_id",
    "screen_id",
    "component_id",
    "test_id",
    "column_id",
    "scenario_id",
    "test_case_id",
    "name",
    "title",
)


def extract_changes(before: Any, after: Any) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    _compare(before, after, "", changes)
    return changes


def group_changes_for_review(
    changes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """필드 단위 diff를 요구사항/엔티티/컬럼/화면 등 업무 항목 단위로 묶습니다."""

    grouped: dict[str, list[dict[str, Any]]] = {}
    for change in changes:
        anchor = _business_anchor(str(change.get("target_path") or "$"))
        grouped.setdefault(anchor, []).append(change)

    results = []
    for anchor, items in grouped.items():
        if len(items) == 1:
            results.append(items[0])
            continue
        change_types = {str(item.get("change_type")) for item in items}
        change_type = next(iter(change_types)) if len(change_types) == 1 else "modified"
        results.append(
            {
                "change_type": change_type,
                "target_path": anchor,
                "title": _group_title(items, anchor),
                "before": [
                    {
                        "path": item.get("target_path"),
                        "value": item.get("before"),
                    }
                    for item in items
                    if item.get("before") is not None
                ],
                "after": [
                    {
                        "path": item.get("target_path"),
                        "value": item.get("after"),
                    }
                    for item in items
                    if item.get("after") is not None
                ],
                "changed_field_count": len(items),
            }
        )
    return results


def _compare(before: Any, after: Any, path: str, changes: list[dict[str, Any]]) -> None:
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(before.keys() | after.keys()):
            child_path = _join(path, str(key))
            if key not in before:
                changes.append(_change("added", child_path, None, after[key], after[key]))
            elif key not in after:
                changes.append(_change("deleted", child_path, before[key], None, before[key]))
            else:
                _compare(before[key], after[key], child_path, changes)
        return

    if isinstance(before, list) and isinstance(after, list):
        before_map = _identity_map(before)
        after_map = _identity_map(after)
        if before_map is not None and after_map is not None:
            for identity in sorted(before_map.keys() | after_map.keys()):
                child_path = _join(path, identity)
                if identity not in before_map:
                    value = after_map[identity]
                    changes.append(_change("added", child_path, None, value, value))
                elif identity not in after_map:
                    value = before_map[identity]
                    changes.append(_change("deleted", child_path, value, None, value))
                else:
                    _compare(
                        before_map[identity],
                        after_map[identity],
                        child_path,
                        changes,
                    )
            return
        if before != after:
            changes.append(_change("modified", path or "$", before, after, after))
        return

    if before != after:
        changes.append(_change("modified", path or "$", before, after, after))


def _identity_map(items: list[Any]) -> dict[str, Any] | None:
    if not items:
        return {}
    if not all(isinstance(item, dict) for item in items):
        return None
    result: dict[str, Any] = {}
    for item in items:
        identity = _identity(item)
        if identity is None or identity in result:
            return None
        result[identity] = item
    return result


def _identity(item: dict[str, Any]) -> str | None:
    for key in IDENTITY_KEYS:
        value = item.get(key)
        if value not in (None, ""):
            return f"{key}={value}"
    return None


def _change(
    change_type: str,
    target_path: str,
    before: Any,
    after: Any,
    context: Any,
) -> dict[str, Any]:
    return {
        "change_type": change_type,
        "target_path": target_path or "$",
        "title": _title(context, target_path),
        "before": before,
        "after": after,
    }


def _title(value: Any, path: str) -> str:
    if isinstance(value, dict):
        for key in ("title", "name", *IDENTITY_KEYS):
            if value.get(key) not in (None, ""):
                return str(value[key])
    return (path.rsplit(".", 1)[-1] if path else "$").replace("=", " ")


def _join(path: str, child: str) -> str:
    return f"{path}.{child}" if path else child


def _business_anchor(path: str) -> str:
    parts = path.split(".")
    last_identity_index = None
    for index, part in enumerate(parts):
        key = part.split("=", 1)[0]
        if "=" in part and key in IDENTITY_KEYS:
            last_identity_index = index
    if last_identity_index is not None:
        return ".".join(parts[: last_identity_index + 1])
    return ".".join(parts[:2]) if len(parts) > 1 else path


def _group_title(items: list[dict[str, Any]], anchor: str) -> str:
    for item in items:
        title = str(item.get("title") or "").strip()
        if title and title not in {"value", "$"}:
            return title
    return anchor.rsplit(".", 1)[-1].replace("=", " ")
