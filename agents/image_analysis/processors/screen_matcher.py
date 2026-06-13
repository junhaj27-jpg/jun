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
    artifacts: list[dict[str, Any]],
    analyses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    screens: list[dict[str, Any]] = []
    used_images: set[str] = set()
    for index, artifact in enumerate(artifacts):
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
