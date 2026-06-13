# 인터페이스 설계서의 구조와 내용을 검증합니다.

from typing import Any

from agents.validation.schemas import duplicate_values, is_empty, make_check, missing_fields
from workflow.state import WorkflowState


TARGET = "image_analysis_agent"
MATCH_STATUSES = {
    "MATCHED",
    "IMAGE_MODIFY_REQUIRED",
    "IMAGE_ADD_REQUIRED",
    "IMAGE_DELETE_CANDIDATE",
    "UNMAPPED_IMAGE",
}


def validate(state: WorkflowState) -> list[dict[str, Any]]:
    items = state.get("agent_outputs", {}).get(TARGET, {}).get(
        "interface_image_analysis_json_list"
    )
    screens = items if isinstance(items, list) else []
    checks = [
        make_check(
            "INTERFACE_OUTPUT_001",
            "인터페이스 출력 존재 검증",
            bool(screens),
            failure_type="INTERFACE_OUTPUT_MISSING",
            message="interface_image_analysis_json_list가 없거나 비어 있습니다.",
            target_agent=TARGET,
        )
    ]
    if not screens:
        return checks

    invalid, missing, mapping_missing, image_missing, status_invalid, message_missing, ux_missing = [], [], [], [], [], [], []
    for index, screen in enumerate(screens):
        scope = str(screen.get("screen_id") or index) if isinstance(screen, dict) else str(index)
        if not isinstance(screen, dict):
            invalid.append(scope)
            continue
        if missing_fields(screen, ["screen_id", "screen_name", "description", "match_status"]):
            missing.append(scope)
        if is_empty(screen.get("matched_requirement_ids")):
            mapping_missing.append(scope)
        if is_empty(screen.get("image_path")) and is_empty(screen.get("image_status")):
            image_missing.append(scope)
        if screen.get("match_status") not in MATCH_STATUSES:
            status_invalid.append(scope)
        if screen.get("match_status") in {"IMAGE_MODIFY_REQUIRED", "IMAGE_ADD_REQUIRED"}:
            description = str(screen.get("description") or "")
            if not any(word in description for word in ("필요", "추가", "수정", "보완")):
                message_missing.append(scope)
        if screen.get("match_status") == "MATCHED" and "UI/UX" not in str(screen.get("description") or ""):
            ux_missing.append(scope)
    checks.extend(
        [
            make_check("INTERFACE_SCHEMA_001", "화면 JSON Schema 검증", not invalid, failure_type="INTERFACE_SCHEMA_ERROR", message="화면 목록에 객체가 아닌 항목이 있습니다.", target_agent=TARGET, target_scope=invalid),
            make_check("INTERFACE_FIELD_001", "화면 필수 필드 검증", not missing, failure_type="INTERFACE_DESCRIPTION_MISSING", message="화면 필수 필드가 누락되었습니다.", target_agent=TARGET, target_scope=missing),
            make_check("INTERFACE_ID_001", "화면 ID 중복 검증", not (duplicates := duplicate_values(screens, "screen_id")), failure_type="INTERFACE_SCREEN_ID_DUPLICATED", message="중복된 screen_id가 있습니다.", target_agent=TARGET, target_scope=duplicates),
            make_check("INTERFACE_REQ_001", "요구사항 화면 매핑 검증", not mapping_missing, failure_type="INTERFACE_REQUIREMENT_MAPPING_MISSING", message="요구사항과 매핑되지 않은 화면이 있습니다.", target_agent=TARGET, target_scope=mapping_missing),
            make_check("INTERFACE_IMAGE_001", "이미지 매핑 검증", not image_missing, failure_type="INTERFACE_IMAGE_MAPPING_MISSING", message="이미지 경로 또는 이미지 상태가 누락되었습니다.", target_agent=TARGET, target_scope=image_missing),
            make_check("INTERFACE_IMAGE_002", "이미지 상태 검증", not status_invalid, failure_type="INTERFACE_IMAGE_STATUS_INVALID", message="허용되지 않은 match_status가 있습니다.", target_agent=TARGET, target_scope=status_invalid),
            make_check("INTERFACE_IMAGE_003", "이미지 보완 요청 문구 검증", not message_missing, failure_type="INTERFACE_IMAGE_UPDATE_MESSAGE_MISSING", message="이미지 수정 또는 추가 필요 문구가 누락되었습니다.", target_agent=TARGET, target_scope=message_missing),
            make_check("INTERFACE_UX_001", "UI/UX 가이드 반영 근거 검증", not ux_missing, failure_type="INTERFACE_UX_GUIDE_NOT_REFLECTED", message="일부 매칭 화면에서 UI/UX 가이드 반영 근거를 확인할 수 없습니다.", target_agent=TARGET, target_scope=ux_missing, severity="MEDIUM", warning=True),
            _meeting_check(state),
        ]
    )
    return checks


def _meeting_check(state: WorkflowState) -> dict[str, Any]:
    if state.get("udt_yn") != "Y":
        return make_check("INTERFACE_MEETING_001", "수정 회의록 반영 검증", True, failure_type="INTERFACE_REQUIREMENT_MAPPING_MISSING", message="", target_agent="document_merge_agent")
    artifact = state.get("agent_outputs", {}).get("document_merge_agent", {}).get("integrated_artifact_json_list")
    return make_check("INTERFACE_MEETING_001", "수정 회의록 반영 검증", bool(artifact), failure_type="INTERFACE_REQUIREMENT_MAPPING_MISSING", message="수정용 통합 산출물을 확인할 수 없습니다.", target_agent="document_merge_agent")
