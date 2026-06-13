# 개별 화면 이미지를 분석하여 구조와 기능을 추출합니다.

from pathlib import Path
from typing import Any

from tools.llm.llm_client import LLMClient
from tools.llm.response_parser import parse_json_response
from tools.llm.send_api import send_parallel


def analyze_images(
    image_paths: list[str],
    *,
    llm_client: LLMClient | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if llm_client is None:
        return [_fallback_analysis(path, index) for index, path in enumerate(image_paths)], []

    requests = [
        {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "화면 이미지를 분석하여 screen_name_candidate, purpose, input_fields, "
                        "buttons, content_areas, user_actions, navigation_candidates를 JSON으로 반환하세요."
                    ),
                },
                {"role": "user", "content": f"분석할 이미지 경로: {path}"},
            ]
        }
        for path in image_paths
    ]
    result = send_parallel(requests, client=llm_client)
    if not result["success"]:
        return (
            [_fallback_analysis(path, index) for index, path in enumerate(image_paths)],
            [{"code": "VISION_LLM_FAILED", "message": result["error"]["message"]}],
        )

    analyses: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for index, (path, llm_result) in enumerate(zip(image_paths, result["data"])):
        if llm_result and llm_result["success"]:
            parsed = parse_json_response(llm_result["data"])
            if parsed["success"] and isinstance(parsed["data"], dict):
                analyses.append(_normalize_analysis(parsed["data"], path, index))
                continue
        analyses.append(_fallback_analysis(path, index))
        warnings.append({"code": "VISION_LLM_ITEM_FALLBACK", "message": "이미지 분석 결과를 기본값으로 대체했습니다.", "image_path": path})
    return analyses, warnings


def _normalize_analysis(data: dict[str, Any], path: str, index: int) -> dict[str, Any]:
    return {
        "analysis_id": f"IMG-{index + 1:03d}",
        "image_path": path,
        "screen_name_candidate": data.get("screen_name_candidate") or data.get("screen_name") or Path(path).stem,
        "purpose": data.get("purpose") or "",
        "input_fields": data.get("input_fields") or [],
        "buttons": data.get("buttons") or [],
        "content_areas": data.get("content_areas") or [],
        "user_actions": data.get("user_actions") or [],
        "navigation_candidates": data.get("navigation_candidates") or [],
    }


def _fallback_analysis(path: str, index: int) -> dict[str, Any]:
    return _normalize_analysis({}, path, index)
