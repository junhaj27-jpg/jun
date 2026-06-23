"""Validation 실패를 대상 제한형 Agent 수정 지시로 변환합니다."""

from typing import Any


REPAIRABLE_FAILURE_TYPES = {
    "ENTITY_GENERIC_NAME",
    "ENTITY_NAME_MISMATCH",
    "ENTITY_NAME_OVERLONG",
    "ENTITY_NAME_SENTENCE",
    "ENTITY_ATTRIBUTE_MISMATCH",
    "ENTITY_DESCRIPTION_MISMATCH",
    "FK_RELATION_MISSING",
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
    "ENTITY_NAME_OVERLONG": {
        "must_fix": ["entity_name을 24자 이하의 짧은 업무 객체 명사형으로 재추론"],
        "must_preserve": ["table_name", "physical_name", "entity_description", "columns", "relationships"],
    },
    "ENTITY_NAME_SENTENCE": {
        "must_fix": ["요구사항 문장형 entity_name을 짧은 업무 객체 명사형으로 재추론"],
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
    "FK_RELATION_MISSING": {
        "must_fix": ["FK 컬럼에 대응하는 기존 부모 엔티티 PK 관계를 확정"],
        "must_preserve": ["table_name", "physical_name", "entity_name", "entity_description", "columns"],
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
    column_scopes = list(
        dict.fromkeys(
            scope
            for scope in scopes
            if "." in scope and _entity_id(scope)
        )
    )
    relationship_scopes = list(
        dict.fromkeys(
            scope
            for scope in scopes
            if "." in scope and not _entity_id(scope)
        )
    )
    must_fix = list(dict.fromkeys(item for kind in failure_types for item in _RULES[kind]["must_fix"]))
    must_preserve = list(
        dict.fromkeys(item for kind in failure_types for item in _RULES[kind]["must_preserve"])
    )
    if {
        "ENTITY_GENERIC_NAME",
        "ENTITY_NAME_MISMATCH",
        "ENTITY_NAME_OVERLONG",
        "ENTITY_NAME_SENTENCE",
    } & set(failure_types):
        must_preserve = [
            item for item in must_preserve if item not in {"entity_name", "logical_name"}
        ]
    if "ENTITY_DESCRIPTION_MISMATCH" in failure_types:
        must_preserve = [
            item for item in must_preserve if item != "entity_description"
        ]
    if "ENTITY_ATTRIBUTE_MISMATCH" in failure_types:
        must_preserve = [item for item in must_preserve if item != "columns"]
    if "FK_RELATION_MISSING" in failure_types:
        must_preserve = [item for item in must_preserve if item != "relationships"]
    forbidden_changes = [
        "전체 ERD 재생성",
        "대상 범위 밖 엔티티 수정",
        "물리 테이블명 또는 물리 컬럼명 수정",
    ]
    if "FK_RELATION_MISSING" not in failure_types:
        forbidden_changes.append("관계 추가/삭제/수정")
    return {
        "repair_id": f"ERD-REPAIR-{repair_round:03d}",
        "repair_round": repair_round,
        "target_agent": "data_structure_design_agent",
        "failure_type": failure_types[0],
        "failure_types": failure_types,
        "target_scope": {
            "entity_ids": entity_ids,
            "column_scopes": column_scopes,
            "relationship_scopes": relationship_scopes,
        },
        "must_fix": must_fix,
        "must_preserve": must_preserve,
        "forbidden_changes": forbidden_changes,
        "validation_checks": checks,
    }


def _entity_id(scope: str) -> str:
    value = str(scope or "").split(".", 1)[0].strip()
    if value.lower() == "all":
        return ""
    return value if value.upper().startswith(("ENT-", "ENTITY-")) else ""
