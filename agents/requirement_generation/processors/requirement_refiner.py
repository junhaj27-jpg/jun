# 비기능 제약사항을 반영하여 요구사항을 정제합니다.

from copy import deepcopy
from typing import Any


def extract_constraints(search_results: list[dict[str, Any]]) -> list[str]:
    constraints: list[str] = []
    seen: set[str] = set()
    for result in search_results:
        text = str(result.get("content") or result.get("title") or "").strip()
        if text and text not in seen:
            constraints.append(text)
            seen.add(text)
    return constraints


def constraints_to_validation_criteria(constraints: list[str]) -> list[str]:
    return [f"{constraint.rstrip('.')} 준수 여부를 확인한다." for constraint in constraints]


def build_final_requirement(
    split_item: dict[str, Any],
    constraints: list[str],
) -> dict[str, Any]:
    item = deepcopy(split_item)
    requirement_id = str(item.get("requirement_id") or item.get("req_id"))
    requirement_name = str(item.get("requirement_name") or item.get("req_name"))
    description = str(item.get("description") or item.get("detail_text") or "")
    source = item.get("source") or item.get("source_req_ids") or []
    if not isinstance(source, list):
        source = [source]
    existing_constraints = item.get("constraints") or []
    if not isinstance(existing_constraints, list):
        existing_constraints = [str(existing_constraints)]
    all_constraints = list(dict.fromkeys([*existing_constraints, *constraints]))
    criteria = constraints_to_validation_criteria(all_constraints)
    return {
        "requirement_id": requirement_id,
        "requirement_name": requirement_name,
        "requirement_type": "기능",
        "description": description,
        "source": source,
        "constraints": all_constraints,
        "priority": item.get("priority", "미지정"),
        "validation_criteria": criteria,
        "note": item.get("note") or ("비기능 요구사항 RAG 검색 결과를 반영함" if constraints else None),
        "req_id": requirement_id,
        "req_name": requirement_name,
        "detail_text": description,
        "source_req_ids": source,
    }
