# 개별 화면 이미지를 분석하여 구조와 기능을 추출합니다.

import base64
import mimetypes
from pathlib import Path
from typing import Any

from tools.llm.llm_client import LLMClient
from tools.llm.response_parser import parse_json_response
from tools.llm.send_api import send_parallel


UI_ELEMENT_ANALYSIS_PROMPT = """
너는 사용자 인터페이스 화면을 관찰하는 UI 분석가다.
현재 이미지만 보고 화면에 실제로 보이는 텍스트와 기능 영역을 추출하라.
요구사항이나 업무 설명은 만들지 말고, 이미지에 보이는 사실만 정리하라.

반드시 JSON으로만 출력하라. 마크다운 금지.

출력 JSON schema:
{
  "screen_name_candidates": ["string"],
  "screen_type": "string",
  "menu_path_candidates": ["string"],
  "visible_texts": ["string"],
  "functional_areas": [
    {
      "name": "string",
      "visible_texts": ["string"],
      "area_role": "string",
      "x_ratio": "number",
      "y_ratio": "number"
    }
  ]
}

작성 규칙:
- 이미지에 실제로 보이는 메뉴명, 제목, 버튼명, 카드명, 표 제목, 차트명, 상태값을 최대한 분리해서 적어라.
- functional_areas는 화면에서 설명 번호를 붙일 만한 기능 영역 단위로 나누어라.
- x_ratio, y_ratio는 각 기능 영역의 대표 위치를 이미지 왼쪽 위 기준 상대 좌표로 적어라.
- 화면에 보이지 않는 업무, 요구사항, 기능은 만들지 마라.
"""


def analyze_images(
    image_paths: list[str],
    *,
    llm_client: LLMClient | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if llm_client is None:
        return [_fallback_analysis(path, index) for index, path in enumerate(image_paths)], []

    warnings: list[dict[str, Any]] = []
    requests = [
        {
            "messages": [
                {
                    "role": "system",
                    "content": UI_ELEMENT_ANALYSIS_PROMPT,
                },
                {"role": "user", "content": build_vision_content(path, warnings)},
            ]
        }
        for path in image_paths
    ]
    result = send_parallel(requests, client=llm_client)
    if not result["success"]:
        return (
            [_fallback_analysis(path, index) for index, path in enumerate(image_paths)],
            [*warnings, {"code": "VISION_LLM_FAILED", "message": result["error"]["message"]}],
        )

    analyses: list[dict[str, Any]] = []
    for index, (path, llm_result) in enumerate(zip(image_paths, result["data"])):
        if llm_result and llm_result["success"]:
            parsed = parse_json_response(llm_result["data"])
            if parsed["success"] and isinstance(parsed["data"], dict):
                analyses.append(_normalize_analysis(parsed["data"], path, index))
                continue
        analyses.append(_fallback_analysis(path, index))
        warnings.append({"code": "VISION_LLM_ITEM_FALLBACK", "message": "이미지 분석 결과를 기본값으로 대체했습니다.", "image_path": path})
    return analyses, warnings


def build_vision_content(path: str, warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "다음 화면 이미지만 보고 실제로 보이는 메뉴명, 제목, 버튼명, 카드명, "
                "표 제목, 차트명, 상태값과 번호 배지를 붙일 기능 영역별 상대 좌표를 JSON으로 추출하세요."
            ),
        }
    ]
    image_url = _image_data_url(path)
    if image_url is None:
        warnings.append(
            {
                "code": "VISION_IMAGE_READ_FAILED",
                "message": "이미지 파일을 읽을 수 없어 경로 텍스트만 전달합니다.",
                "image_path": path,
            }
        )
        content.append({"type": "text", "text": f"이미지 경로: {path}"})
        return content
    content.append({"type": "image_url", "image_url": {"url": image_url}})
    return content


def _image_data_url(path: str) -> str | None:
    image_path = Path(path)
    if not image_path.exists() or not image_path.is_file():
        return None
    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _normalize_analysis(data: dict[str, Any], path: str, index: int) -> dict[str, Any]:
    screen_names = _string_list(data.get("screen_name_candidates"))
    menu_paths = _string_list(data.get("menu_path_candidates"))
    visible_texts = _string_list(data.get("visible_texts"))
    input_fields = _string_list(data.get("input_fields"))
    buttons = _string_list(data.get("buttons"))
    user_actions = _string_list(data.get("user_actions"))
    content_areas = data.get("content_areas") or []
    functional_areas = _normalize_functional_areas(data.get("functional_areas") or content_areas or [])
    screen_name = (
        data.get("screen_name_candidate")
        or data.get("screen_name")
        or (screen_names[0] if screen_names else "")
        or Path(path).stem
    )
    return {
        "analysis_id": f"IMG-{index + 1:03d}",
        "image_path": path,
        "screen_name_candidate": screen_name,
        "screen_name_candidates": screen_names or [str(screen_name)],
        "screen_type": str(data.get("screen_type") or ""),
        "menu_path_candidates": menu_paths,
        "visible_texts": visible_texts,
        "purpose": data.get("purpose") or "",
        "input_fields": input_fields,
        "buttons": buttons,
        "content_areas": content_areas,
        "functional_areas": functional_areas,
        "user_actions": user_actions,
        "navigation_candidates": _string_list(data.get("navigation_candidates")),
    }


def _fallback_analysis(path: str, index: int) -> dict[str, Any]:
    name = Path(path).stem
    return _normalize_analysis(
        {
            "screen_name_candidates": [name],
            "screen_type": "업무 화면",
            "menu_path_candidates": [name],
            "visible_texts": [name, "조회", "검색", "상세", "저장"],
            "functional_areas": [
                {
                    "name": "화면 제목 및 메뉴 영역",
                    "visible_texts": [name],
                    "area_role": "사용자가 현재 화면과 업무 위치를 확인한다.",
                    "x_ratio": 0.18,
                    "y_ratio": 0.12,
                },
                {
                    "name": "검색 조건 영역",
                    "visible_texts": ["검색", "조회"],
                    "area_role": "사용자가 조건을 입력하고 목록을 조회한다.",
                    "x_ratio": 0.22,
                    "y_ratio": 0.28,
                },
                {
                    "name": "목록 및 현황 영역",
                    "visible_texts": ["목록", "현황", "상태"],
                    "area_role": "시스템이 조회 결과와 업무 상태를 목록 또는 카드 형태로 표시한다.",
                    "x_ratio": 0.48,
                    "y_ratio": 0.52,
                },
                {
                    "name": "상세 처리 영역",
                    "visible_texts": ["상세", "저장", "처리"],
                    "area_role": "사용자가 선택한 항목의 상세 내용을 확인하고 필요한 처리를 수행한다.",
                    "x_ratio": 0.78,
                    "y_ratio": 0.72,
                },
            ],
        },
        path,
        index,
    )


def _normalize_functional_areas(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    areas = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, dict):
            areas.append(
                {
                    "name": str(item.get("name") or item.get("title") or f"기능 영역 {index}"),
                    "visible_texts": item.get("visible_texts") if isinstance(item.get("visible_texts"), list) else [],
                    "area_role": str(item.get("area_role") or item.get("description") or ""),
                    "x_ratio": _safe_ratio(item.get("x_ratio"), 0.2 + ((index - 1) % 3) * 0.3),
                    "y_ratio": _safe_ratio(item.get("y_ratio"), 0.18 + min(index - 1, 6) * 0.1),
                }
            )
        else:
            areas.append(
                {
                    "name": str(item),
                    "visible_texts": [str(item)],
                    "area_role": "",
                    "x_ratio": 0.2 + ((index - 1) % 3) * 0.3,
                    "y_ratio": 0.18 + min(index - 1, 6) * 0.1,
                }
            )
    return areas


def _safe_ratio(value: Any, default: float) -> float:
    try:
        return max(0.03, min(0.97, float(value)))
    except Exception:
        return default


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
