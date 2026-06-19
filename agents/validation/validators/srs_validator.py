# 요구사항 정의서의 구조와 내용을 검증합니다.

from typing import Any

from agents.validation.schemas import duplicate_values, is_empty, make_check, missing_fields
from workflow.state import WorkflowState


TARGET = "requirement_generation_agent"
UPDATE_TARGET = "document_merge_agent"


def validate(state: WorkflowState) -> list[dict[str, Any]]:
    target, output_key = _target_output_for_mode(state)
    output = state.get("agent_outputs", {}).get(target, {})
    requirements = output.get(output_key)
    raw_items = requirements if isinstance(requirements, list) else []
    items = [item for item in raw_items if isinstance(item, dict)]
    checks = [
        make_check(
            "SRS_OUTPUT_001",
            "요구사항 출력 존재 검증",
            bool(raw_items),
            failure_type="SRS_OUTPUT_MISSING",
            message=f"{output_key}가 없거나 비어 있습니다.",
            target_agent=target,
        )
    ]
    if not raw_items:
        return checks

    invalid = [str(index) for index, item in enumerate(raw_items) if not isinstance(item, dict)]
    checks.append(
        make_check(
            "SRS_SCHEMA_001",
            "요구사항 JSON Schema 검증",
            not invalid,
            failure_type="SRS_SCHEMA_ERROR",
            message="요구사항 목록에 객체가 아닌 항목이 있습니다.",
            target_agent=target,
            target_scope=invalid,
        )
    )

    missing = []
    source_missing = []
    for index, item in enumerate(items):
        req_id = _requirement_id(item, index)
        if _missing_requirement_fields(item):
            missing.append(req_id)
        if is_empty(item.get("source_req_ids")) and is_empty(item.get("source_refs")) and is_empty(item.get("source")):
            source_missing.append(req_id)
    checks.extend(
        [
            make_check(
                "SRS_FIELD_001",
                "필수 필드 검증",
                not missing,
                failure_type="SRS_REQUIRED_FIELD_MISSING",
                message="일부 요구사항에 필수 필드가 누락되었습니다.",
                target_agent=target,
                target_scope=missing,
            ),
            make_check(
                "SRS_DUPLICATE_001",
                "요구사항 ID 중복 검증",
                not (duplicates := duplicate_values(items, "req_id", "requirement_id")),
                failure_type="SRS_DUPLICATE_REQ_ID",
                message="중복된 req_id가 있습니다.",
                target_agent=target,
                target_scope=duplicates,
            ),
            make_check(
                "SRS_DUPLICATE_002",
                "요구사항명 중복 검증",
                not (names := duplicate_values(items, "req_name", "requirement_name")),
                failure_type="SRS_DUPLICATE_REQUIREMENT",
                message="중복된 요구사항명이 있습니다.",
                target_agent=target,
                target_scope=names,
                severity="MEDIUM",
            ),
            make_check(
                "SRS_TRACE_001",
                "원본 요구사항 추적성 검증",
                not source_missing,
                failure_type="SRS_SOURCE_TRACE_MISSING",
                message="원본 RFP 요구사항을 추적할 source 정보가 누락되었습니다.",
                target_agent=target,
                target_scope=source_missing,
            ),
        ]
    )

    types = {str(item.get("requirement_type", "")).lower() for item in items if isinstance(item, dict)}
    functional = [
        item for item in items
        if isinstance(item, dict)
        and _is_functional_type(item.get("requirement_type") or item.get("type"))
    ]
    has_non_functional = any(
        value and not _is_functional_type(value) for value in types
    ) or any(item.get("constraints") for item in items if isinstance(item, dict))
    work_unit_invalid = [
        str(item.get("req_id") or index)
        for index, item in enumerate(functional)
        if is_empty(item.get("validation_criteria"))
    ]
    checks.extend(
        [
        make_check(
            "SRS_FUNCTION_001",
            "기능 요구사항 존재 검증",
            bool(functional),
            failure_type="SRS_WORK_UNIT_INVALID",
            message="업무 단위로 분해된 기능 요구사항이 없습니다.",
            target_agent=target,
        ),
        make_check(
            "SRS_NFR_001",
            "비기능 요구사항 반영 검증",
            has_non_functional,
            failure_type="SRS_NON_FUNCTIONAL_MISSING",
            message="비기능 요구사항을 확인할 수 없습니다.",
            target_agent=target,
            severity="MEDIUM",
            warning=True,
        ),
        make_check(
            "SRS_WORK_UNIT_001",
            "업무 단위 검증 기준 존재 여부",
            not work_unit_invalid,
            failure_type="SRS_WORK_UNIT_INVALID",
            message="일부 기능 요구사항에 validation_criteria가 없습니다.",
            target_agent=target,
            target_scope=work_unit_invalid,
            severity="MEDIUM",
            warning=True,
        ),
        _meeting_check(state, items),
        ]
    )
    return checks


def _target_output_for_mode(state: WorkflowState) -> tuple[str, str]:
    if state.get("udt_yn") == "Y":
        return UPDATE_TARGET, "integrated_artifact_json_list"
    return TARGET, "final_requirement_json_list"


def _meeting_check(state: WorkflowState, items: list[dict[str, Any]]) -> dict[str, Any]:
    changes = state.get("agent_outputs", {}).get("document_merge_agent", {}).get("meeting_change_items")
    required = state.get("udt_yn") == "Y" and bool(changes)
    reflected = any(item.get("meeting_change_ids") or item.get("meeting_ref") for item in items)
    return make_check(
        "SRS_MEETING_001",
        "회의록 변경사항 반영 검증",
        not required or reflected,
        failure_type="SRS_MEETING_CHANGE_MISSING",
        message="회의록 변경사항 반영 근거를 확인할 수 없습니다.",
        target_agent="document_merge_agent",
    )


def _requirement_id(item: dict[str, Any], index: int) -> str:
    return str(item.get("req_id") or item.get("requirement_id") or item.get("id") or index)


def _missing_requirement_fields(item: dict[str, Any]) -> bool:
    required_groups = [
        ("req_id", "requirement_id"),
        ("req_name", "requirement_name"),
        ("requirement_type", "type"),
        ("detail_text", "description"),
    ]
    return any(all(is_empty(item.get(key)) for key in group) for group in required_groups)


def _is_functional_type(value: Any) -> bool:
    requirement_type = str(value or "").strip().lower()
    return requirement_type.startswith("기능") or requirement_type.startswith("functional") or requirement_type == "function"
