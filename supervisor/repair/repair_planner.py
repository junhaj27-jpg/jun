"""Validation 실패를 대상 제한형 Agent 수정 지시로 변환합니다."""

from typing import Any


REPAIRABLE_FAILURE_TYPES = {
    "ENTITY_GENERIC_NAME",
    "ENTITY_NAME_MISMATCH",
    "ENTITY_ATTRIBUTE_MISMATCH",
    "ENTITY_DESCRIPTION_MISMATCH",
}

_RULES: dict[str, dict[str, list[str]]] = {
    "ENTITY_GENERIC_NAME": {
        "must_fix": ["generic entity_name을 실제 업무 엔티티명으로 재추론"],
        "must_preserve": ["table_name", "physical_name", "entity_description", "columns", "relationships"],
    },
    "ENTITY_NAME_MISMATCH": {
        "must_fix": ["entity_name을 설명과 대표 속성에 맞게 재추론"],
        "must_preserve": ["table_name", "physical_name", "entity_description", "columns", "relationships"],
    },
    "ENTITY_ATTRIBUTE_MISMATCH": {
        "must_fix": ["대상 속성의 attribute_name을 엔티티와 컬럼 의미에 맞게 재추론"],
        "must_preserve": ["table_name", "physical_name", "entity_name", "entity_description", "column_name", "data_type", "relationships"],
    },
    "ENTITY_DESCRIPTION_MISMATCH": {
        "must_fix": ["entity_description을 엔티티의 목적을 설명하는 한 문장으로 재작성"],
        "must_preserve": ["table_name", "physical_name", "entity_name", "columns", "relationships"],
    },
}


def build_repair_instruction(
    failure: dict[str, Any],
    *,
    repair_round: int,
) -> dict[str, Any] | None:
    """ERD 의미 정합성 실패만 제한 수정 지시로 변환합니다."""

    checks = [
        check
        for check in failure.get("failed_checks", [])
        if str(check.get("failure_type") or "") in REPAIRABLE_FAILURE_TYPES
        and check.get("target_agent") == "data_structure_design_agent"
    ]
    if not checks:
        return None

    failure_types = list(dict.fromkeys(str(check["failure_type"]) for check in checks))
    scopes = [str(scope) for check in checks for scope in check.get("target_scope", [])]
    entity_ids = list(dict.fromkeys(_entity_id(scope) for scope in scopes if _entity_id(scope)))
    column_scopes = list(dict.fromkeys(scope for scope in scopes if "." in scope))
    must_fix = list(dict.fromkeys(item for kind in failure_types for item in _RULES[kind]["must_fix"]))
    must_preserve = list(
        dict.fromkeys(item for kind in failure_types for item in _RULES[kind]["must_preserve"])
    )
    return {
        "repair_id": f"ERD-REPAIR-{repair_round:03d}",
        "repair_round": repair_round,
        "target_agent": "data_structure_design_agent",
        "failure_type": failure_types[0],
        "failure_types": failure_types,
        "target_scope": {
            "entity_ids": entity_ids,
            "column_scopes": column_scopes,
        },
        "must_fix": must_fix,
        "must_preserve": must_preserve,
        "forbidden_changes": [
            "전체 ERD 재생성",
            "대상 범위 밖 엔티티 수정",
            "물리 테이블명 또는 물리 컬럼명 수정",
            "관계 추가/삭제/수정",
        ],
        "validation_checks": checks,
    }


def _entity_id(scope: str) -> str:
    value = str(scope or "").split(".", 1)[0].strip()
    return "" if value.lower() == "all" else value
