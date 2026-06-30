# 요구사항, 화면 정보 및 이미지 간의 관계를 매핑합니다.

from typing import Any


GENERIC_MATCH_TOKENS = {
    "화면",
    "기능",
    "제공",
    "사용자",
    "요구사항",
    "screen",
    "function",
}


def match_creation_screens(
    requirements: list[dict[str, Any]],
    analyses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    screens: list[dict[str, Any]] = []
    matched_ids: set[str] = set()
    for index, analysis in enumerate(analyses):
        matched = [
            req for req in requirements if _matches(req, analysis)
        ]
        ids = [_requirement_id(req) for req in matched]
        matched_ids.update(ids)
        screens.append(
            {
                "screen_id": f"SCR-{index + 1:03d}",
                "screen_name": analysis["screen_name_candidate"],
                "image_path": analysis["image_path"],
                "image_status": "AVAILABLE",
                "match_status": "MATCHED" if ids else "UNMAPPED_IMAGE",
                "matched_requirement_ids": ids,
                "analysis": analysis,
            }
        )

    for requirement in requirements:
        requirement_id = _requirement_id(requirement)
        if requirement_id in matched_ids:
            continue
        if not _should_create_missing_screen(requirement):
            continue
        screens.append(
            {
                "screen_id": f"SCR-{len(screens) + 1:03d}",
                "screen_name": _requirement_name(requirement),
                "image_path": None,
                "image_status": "IMAGE_ADD_REQUIRED",
                "match_status": "IMAGE_ADD_REQUIRED",
                "matched_requirement_ids": [requirement_id],
                "analysis": {},
            }
        )
    return screens


def match_update_screens(
    artifacts: list[Any],
    analyses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    screens: list[dict[str, Any]] = []
    used_images: set[str] = set()
    for index, raw_artifact in enumerate(artifacts):
        artifact = _normalize_update_artifact(raw_artifact, index)
        matched = next((analysis for analysis in analyses if _matches(artifact, analysis)), None)
        if matched:
            used_images.add(matched["image_path"])
        status = "MATCHED" if matched and not _needs_image_update(artifact, matched) else (
            "IMAGE_MODIFY_REQUIRED" if matched else "IMAGE_ADD_REQUIRED"
        )
        screens.append(
            {
                "screen_id": str(artifact.get("screen_id") or f"SCR-{index + 1:03d}"),
                "screen_name": str(artifact.get("screen_name") or artifact.get("name") or f"화면 {index + 1}"),
                "image_path": matched.get("image_path") if matched else None,
                "image_status": status,
                "match_status": status,
                "matched_requirement_ids": artifact.get("matched_requirement_ids") or artifact.get("requirement_ids") or ["UNKNOWN"],
                "analysis": matched or {},
                "artifact": artifact,
            }
        )
    for analysis in analyses:
        if analysis["image_path"] not in used_images:
            screens.append(
                {
                    "screen_id": f"SCR-{len(screens) + 1:03d}",
                    "screen_name": analysis["screen_name_candidate"],
                    "image_path": analysis["image_path"],
                    "image_status": "IMAGE_DELETE_CANDIDATE",
                    "match_status": "IMAGE_DELETE_CANDIDATE",
                    "matched_requirement_ids": ["UNKNOWN"],
                    "analysis": analysis,
                }
            )
    return screens


def _normalize_update_artifact(item: Any, index: int) -> dict[str, Any]:
    """기존 INTERFACE 산출물이 비구조 텍스트로 파싱돼도 수정 흐름이 죽지 않게 보정합니다."""

    if isinstance(item, dict):
        return item

    text = _artifact_text(item).strip()
    screen_name = _guess_screen_name(text, index)
    return {
        "screen_id": f"SCR-{index + 1:03d}",
        "screen_name": screen_name,
        "name": screen_name,
        "description": text,
        "screen_overview": text,
        "matched_requirement_ids": ["UNKNOWN"],
        "parse_warning": "INTERFACE artifact was not structured and was normalized from text.",
    }


def _artifact_text(item: Any) -> str:
    if item is None:
        return ""
    if isinstance(item, (list, tuple, set)):
        return " ".join(_artifact_text(value) for value in item if value is not None)
    return str(item)


def _guess_screen_name(text: str, index: int) -> str:
    for line in text.splitlines():
        candidate = line.strip()
        if candidate:
            return candidate[:80]
    return f"화면 {index + 1}"


def _matches(requirement: dict[str, Any], analysis: dict[str, Any]) -> bool:
    requirement_text = " ".join(
        str(requirement.get(key) or "")
        for key in ("req_name", "requirement_name", "screen_name", "name", "detail_text", "description")
    ).lower()
    analysis_text = " ".join(
        str(analysis.get(key) or "")
        for key in ("screen_name_candidate", "purpose", "image_path")
    ).lower()
    tokens = {
        token
        for token in requirement_text.replace("_", " ").split()
        if len(token) >= 2 and token not in GENERIC_MATCH_TOKENS
    }
    return any(token in analysis_text for token in tokens)


def _needs_image_update(artifact: dict[str, Any], analysis: dict[str, Any]) -> bool:
    expected_fields = artifact.get("input_fields") or []
    actual_fields = analysis.get("input_fields") or []
    return bool(expected_fields and not set(map(str, expected_fields)).issubset(set(map(str, actual_fields))))


def _requirement_id(item: dict[str, Any]) -> str:
    return str(item.get("req_id") or item.get("requirement_id") or item.get("screen_id") or "UNKNOWN")


def _requirement_name(item: dict[str, Any]) -> str:
    return str(item.get("req_name") or item.get("requirement_name") or item.get("screen_name") or "신규 화면")


def _should_create_missing_screen(requirement: dict[str, Any]) -> bool:
    """생성 모드에서 실제 화면 산출물이 필요한 요구사항만 이미지 추가 대상으로 둡니다."""

    requirement_type = str(requirement.get("requirement_type") or requirement.get("type") or "").strip()
    if "비기능" in requirement_type:
        return False
    text = " ".join(
        str(requirement.get(key) or "")
        for key in ("req_name", "requirement_name", "screen_name", "name", "detail_text", "description")
    ).lower()
    screen_keywords = (
        "화면",
        "페이지",
        "메뉴",
        "버튼",
        "입력",
        "조회",
        "등록",
        "수정",
        "삭제",
        "대시보드",
        "ui",
        "ux",
        "screen",
        "page",
        "menu",
    )
    return any(keyword in text for keyword in screen_keywords)
