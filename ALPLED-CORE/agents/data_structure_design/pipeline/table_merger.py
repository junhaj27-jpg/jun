"""유사 테이블 후보를 병합하고 정렬합니다."""

from typing import Any

from agents.data_structure_design.pipeline.rule_engine import TYPE_PRIORITY


def merge_table_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        table_name = str(candidate.get("table_name") or "").strip()
        if not table_name:
            continue
        current = merged.get(table_name)
        if current is None:
            merged[table_name] = {
                **candidate,
                "source_requirement_ids": _source_ids(candidate),
            }
            continue
        current["source_requirement_ids"] = list(
            dict.fromkeys([*current.get("source_requirement_ids", []), *_source_ids(candidate)])
        )
        if len(str(candidate.get("reason") or "")) > len(str(current.get("reason") or "")):
            current["reason"] = candidate["reason"]
    return sorted(
        merged.values(),
        key=lambda item: (TYPE_PRIORITY.get(str(item.get("table_type")), 999), str(item.get("table_name"))),
    )


def _source_ids(candidate: dict[str, Any]) -> list[str]:
    value = candidate.get("source_requirement_ids")
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    if value not in (None, ""):
        return [str(value)]
    return []
