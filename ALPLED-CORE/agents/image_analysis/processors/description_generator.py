# 분석된 화면에 대한 설명과 이미지 보완 문구를 생성합니다.

from typing import Any


def build_description(
    screen: dict[str, Any],
    *,
    ux_guides: list[dict[str, Any]],
    interface_requirements: list[dict[str, Any]],
) -> str:
    status = screen["match_status"]
    name = screen["screen_name"]
    if status == "IMAGE_ADD_REQUIRED":
        return f"{name} 요구사항에 대응하는 화면 이미지가 없습니다. 해당 화면에 대한 이미지 추가가 필요합니다."
    if status == "UNMAPPED_IMAGE":
        return f"{name} 이미지는 요구사항과 매칭되지 않았습니다. 사용 여부 확인이 필요합니다."
    if status == "IMAGE_MODIFY_REQUIRED":
        return f"{name} 화면의 변경 요구사항이 기존 이미지에 반영되지 않아 화면 이미지 수정이 필요합니다."
    if status == "IMAGE_DELETE_CANDIDATE":
        return f"{name} 이미지는 수정 산출물과 매칭되지 않아 삭제 가능 여부 확인이 필요합니다."
    purpose = screen.get("analysis", {}).get("purpose") or f"{name} 기능을 제공하는 화면"
    references = len(ux_guides) + len(interface_requirements)
    return f"{purpose}입니다. 관련 UI/UX 및 인터페이스 참고사항 {references}건을 반영합니다."


def build_image_request_message(screen: dict[str, Any]) -> str:
    status = screen["match_status"]
    name = screen["screen_name"]
    if status == "IMAGE_ADD_REQUIRED":
        return f"{name}에 대응하는 화면 이미지 추가가 필요합니다."
    if status == "UNMAPPED_IMAGE":
        return f"{name} 이미지는 요구사항과 매칭되지 않은 이미지입니다. 사용 여부 확인이 필요합니다."
    if status == "IMAGE_MODIFY_REQUIRED":
        return f"{name} 화면의 변경사항 반영을 위해 이미지 수정이 필요합니다."
    if status == "IMAGE_DELETE_CANDIDATE":
        return f"{name} 이미지는 수정 산출물과 매칭되지 않아 삭제 가능 여부 확인이 필요합니다."
    return ""
