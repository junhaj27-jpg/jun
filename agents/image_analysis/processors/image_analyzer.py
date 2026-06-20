# 개별 화면 이미지를 분석하여 OCR 좌표, 화면 구조와 기능 컴포넌트를 추출합니다.

import base64
import mimetypes
import statistics
from pathlib import Path
from typing import Any

from tools.llm.llm_client import LLMClient
from tools.llm.response_parser import parse_json_response
from tools.llm.send_api import send_parallel


UI_ELEMENT_ANALYSIS_PROMPT = """
너는 사용자 인터페이스 화면을 관찰하는 UI 분석가다.
현재 이미지와 OCR 텍스트 좌표를 함께 보고 화면에 실제로 보이는 텍스트, UI 컴포넌트 후보, 기능 영역을 추출하라.
요구사항이나 업무 설명은 만들지 말고, 이미지에 보이는 사실만 정리하라.

반드시 JSON으로만 출력하라. 마크다운 금지.

출력 JSON schema:
{
  "screen_name_candidates": ["string"],
  "screen_type": "string",
  "menu_path_candidates": ["string"],
  "visible_texts": ["string"],
  "ocr_texts": [
    {
      "text": "string",
      "x1": "number",
      "y1": "number",
      "x2": "number",
      "y2": "number"
    }
  ],
  "component_candidates": [
    {
      "candidate_id": "string",
      "component_name": "string",
      "component_type": "button|input|search_filter|table|card|menu|form|chart|content|unknown",
      "texts": ["string"],
      "bbox": {"x1": "number", "y1": "number", "x2": "number", "y2": "number"},
      "x_ratio": "number",
      "y_ratio": "number",
      "reason": "string"
    }
  ],
  "functional_areas": [
    {
      "name": "string",
      "visible_texts": ["string"],
      "area_role": "string",
      "component_type": "string",
      "bbox": {"x1": "number", "y1": "number", "x2": "number", "y2": "number"},
      "x_ratio": "number",
      "y_ratio": "number"
    }
  ]
}

작성 규칙:
- 이미지에 실제로 보이는 메뉴명, 제목, 버튼명, 카드명, 표 제목, 차트명, 상태값을 최대한 분리해서 적어라.
- OCR 텍스트 좌표와 이미지에서 보이는 배치를 대조하여 서로 같은 UI 컴포넌트에 속하는 텍스트를 component_candidates로 묶어라.
- component_candidates는 번호 배지를 붙일 수 있는 업무 의미 단위로 만들고, 단순 장식/중복 텍스트는 제외하라.
- functional_areas는 component_candidates를 바탕으로 화면설계서 처리내용에 들어갈 기능 영역 단위로 나누어라.
- bbox, x_ratio, y_ratio는 반드시 이미지 왼쪽 위 기준 0~1 상대 좌표로 적어라. 픽셀 좌표를 쓰지 마라.
- 화면에 보이지 않는 업무, 요구사항, 기능은 만들지 마라.
"""


def analyze_images(
    image_paths: list[str],
    *,
    llm_client: LLMClient | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ocr_by_path: dict[str, list[dict[str, Any]]] = {}
    ocr_candidates_by_path: dict[str, list[dict[str, Any]]] = {}
    for path in image_paths:
        ocr_items = extract_ocr_texts(path)
        ocr_by_path[path] = ocr_items
        ocr_candidates_by_path[path] = build_component_candidates_from_ocr(ocr_items)

    if llm_client is None:
        return [
            _fallback_analysis(
                path,
                index,
                ocr_texts=ocr_by_path.get(path, []),
                component_candidates=ocr_candidates_by_path.get(path, []),
            )
            for index, path in enumerate(image_paths)
        ], []

    warnings: list[dict[str, Any]] = []
    requests = [
        {
            "messages": [
                {
                    "role": "system",
                    "content": UI_ELEMENT_ANALYSIS_PROMPT,
                },
                {
                    "role": "user",
                    "content": build_vision_content(
                        path,
                        warnings,
                        ocr_texts=ocr_by_path.get(path, []),
                        component_candidates=ocr_candidates_by_path.get(path, []),
                    ),
                },
            ]
        }
        for path in image_paths
    ]
    result = send_parallel(requests, client=llm_client)
    if not result["success"]:
        return (
            [
                _fallback_analysis(
                    path,
                    index,
                    ocr_texts=ocr_by_path.get(path, []),
                    component_candidates=ocr_candidates_by_path.get(path, []),
                )
                for index, path in enumerate(image_paths)
            ],
            [*warnings, {"code": "VISION_LLM_FAILED", "message": result["error"]["message"]}],
        )

    analyses: list[dict[str, Any]] = []
    for index, (path, llm_result) in enumerate(zip(image_paths, result["data"])):
        if llm_result and llm_result["success"]:
            parsed = parse_json_response(llm_result["data"])
            if parsed["success"] and isinstance(parsed["data"], dict):
                analyses.append(
                    _normalize_analysis(
                        parsed["data"],
                        path,
                        index,
                        ocr_texts=ocr_by_path.get(path, []),
                        component_candidates=ocr_candidates_by_path.get(path, []),
                    )
                )
                continue
        analyses.append(
            _fallback_analysis(
                path,
                index,
                ocr_texts=ocr_by_path.get(path, []),
                component_candidates=ocr_candidates_by_path.get(path, []),
            )
        )
        warnings.append({"code": "VISION_LLM_ITEM_FALLBACK", "message": "이미지 분석 결과를 기본값으로 대체했습니다.", "image_path": path})
    return analyses, warnings


def build_vision_content(
    path: str,
    warnings: list[dict[str, Any]],
    *,
    ocr_texts: list[dict[str, Any]] | None = None,
    component_candidates: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    ocr_texts = ocr_texts or []
    component_candidates = component_candidates or []
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "다음 화면 이미지와 OCR 좌표 후보를 함께 보고 실제 UI 컴포넌트 단위로 묶어 JSON으로 추출하세요.\n"
                f"OCR_TEXTS={ocr_texts[:120]}\n"
                f"COMPONENT_CANDIDATES={component_candidates[:40]}"
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


def extract_ocr_texts(path: str) -> list[dict[str, Any]]:
    """설치된 OCR 엔진이 있으면 텍스트와 bounding box를 추출합니다."""

    image_path = Path(path)
    if not image_path.exists() or not image_path.is_file():
        return []
    try:
        import pytesseract  # type: ignore
        from PIL import Image
    except Exception:
        return []

    try:
        with Image.open(image_path) as image:
            width, height = image.size
            raw = pytesseract.image_to_data(
                image,
                lang="kor+eng",
                output_type=pytesseract.Output.DICT,
            )
    except Exception:
        return []

    items: list[dict[str, Any]] = []
    for index, text in enumerate(raw.get("text", [])):
        value = str(text or "").strip()
        if not value:
            continue
        try:
            confidence = float(raw.get("conf", [])[index])
        except Exception:
            confidence = 0.0
        if confidence < 35:
            continue
        left = float(raw["left"][index])
        top = float(raw["top"][index])
        box_width = float(raw["width"][index])
        box_height = float(raw["height"][index])
        items.append(
            {
                "text": value,
                "x1": left,
                "y1": top,
                "x2": left + box_width,
                "y2": top + box_height,
                "image_width": width,
                "image_height": height,
                "x_ratio": _safe_ratio((left + box_width / 2) / max(1, width), 0.5),
                "y_ratio": _safe_ratio((top + box_height / 2) / max(1, height), 0.5),
                "confidence": confidence,
            }
        )
    return items


def build_component_candidates_from_ocr(ocr_texts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """OCR bounding box를 줄/인접성 기준으로 묶어 컴포넌트 후보를 만듭니다."""

    items = [_normalize_ocr_item(item) for item in ocr_texts if _normalize_ocr_item(item)]
    if not items:
        return []

    heights = [item["y2"] - item["y1"] for item in items if item["y2"] > item["y1"]]
    y_threshold = max(12.0, statistics.median(heights) * 1.25) if heights else 16.0
    sorted_items = sorted(items, key=lambda item: (item["cy"], item["x1"]))
    lines: list[list[dict[str, Any]]] = []
    for item in sorted_items:
        if not lines:
            lines.append([item])
            continue
        line_center = statistics.mean(value["cy"] for value in lines[-1])
        if abs(item["cy"] - line_center) <= y_threshold:
            lines[-1].append(item)
        else:
            lines.append([item])

    candidates: list[dict[str, Any]] = []
    for line_index, line in enumerate(lines, start=1):
        line = sorted(line, key=lambda item: item["x1"])
        for group_index, group in enumerate(_split_line_by_gap(line), start=1):
            texts = [item["text"] for item in group if item["text"]]
            if not texts:
                continue
            bbox = _bbox_for_items(group)
            component_type = _component_type_hint(texts, bbox)
            candidates.append(
                {
                    "candidate_id": f"OCR-{line_index:02d}-{group_index:02d}",
                    "component_name": _component_name_from_texts(texts, component_type),
                    "component_type": component_type,
                    "texts": texts,
                    "bbox": bbox,
                    "x_ratio": _safe_ratio((bbox["x1"] + bbox["x2"]) / 2, 0.5),
                    "y_ratio": _safe_ratio((bbox["y1"] + bbox["y2"]) / 2, 0.5),
                    "layout_hint": "same_line_nearby_text",
                }
            )
    return _merge_related_candidates(candidates)


def _image_data_url(path: str) -> str | None:
    image_path = Path(path)
    if not image_path.exists() or not image_path.is_file():
        return None
    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _normalize_analysis(
    data: dict[str, Any],
    path: str,
    index: int,
    *,
    ocr_texts: list[dict[str, Any]] | None = None,
    component_candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    screen_names = _string_list(data.get("screen_name_candidates"))
    menu_paths = _string_list(data.get("menu_path_candidates"))
    visible_texts = _string_list(data.get("visible_texts"))
    ocr_items = _normalize_ocr_items(data.get("ocr_texts")) or _normalize_ocr_items(ocr_texts)
    input_fields = _string_list(data.get("input_fields"))
    buttons = _string_list(data.get("buttons"))
    user_actions = _string_list(data.get("user_actions"))
    content_areas = data.get("content_areas") or []
    raw_candidates = data.get("component_candidates")
    candidates = _normalize_component_candidates(raw_candidates) or _normalize_component_candidates(component_candidates)
    if not candidates and ocr_items:
        candidates = build_component_candidates_from_ocr(ocr_items)
    functional_areas = _normalize_functional_areas(data.get("functional_areas") or content_areas or [])
    if not functional_areas and candidates:
        functional_areas = _functional_areas_from_candidates(candidates)
    screen_name = (
        data.get("screen_name_candidate")
        or data.get("screen_name")
        or (screen_names[0] if screen_names else "")
        or _screen_name_from_candidates(candidates)
        or Path(path).stem
    )
    return {
        "analysis_id": f"IMG-{index + 1:03d}",
        "image_path": path,
        "screen_name_candidate": screen_name,
        "screen_name_candidates": screen_names or [str(screen_name)],
        "screen_type": str(data.get("screen_type") or ""),
        "menu_path_candidates": menu_paths,
        "visible_texts": visible_texts or [item["text"] for item in ocr_items],
        "ocr_texts": ocr_items,
        "component_candidates": candidates,
        "purpose": data.get("purpose") or "",
        "input_fields": input_fields,
        "buttons": buttons,
        "content_areas": content_areas,
        "functional_areas": functional_areas,
        "user_actions": user_actions,
        "navigation_candidates": _string_list(data.get("navigation_candidates")),
    }


def _fallback_analysis(
    path: str,
    index: int,
    *,
    ocr_texts: list[dict[str, Any]] | None = None,
    component_candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    name = Path(path).stem
    candidates = _normalize_component_candidates(component_candidates)
    if not candidates:
        candidates = build_component_candidates_from_ocr(_normalize_ocr_items(ocr_texts))
    functional_areas = _functional_areas_from_candidates(candidates)
    if not functional_areas:
        functional_areas = [
            {
                "name": name,
                "visible_texts": [name],
                "area_role": "이미지에서 식별된 화면 전체 영역입니다.",
                "component_type": "content",
                "bbox": {"x1": 0.08, "y1": 0.08, "x2": 0.92, "y2": 0.92},
                "x_ratio": 0.5,
                "y_ratio": 0.5,
            }
        ]
    return _normalize_analysis(
        {
            "screen_name_candidates": [name],
            "screen_type": "업무 화면",
            "menu_path_candidates": [name],
            "visible_texts": [item["text"] for item in _normalize_ocr_items(ocr_texts)] or [name],
            "ocr_texts": ocr_texts or [],
            "component_candidates": candidates,
            "functional_areas": functional_areas,
        },
        path,
        index,
        ocr_texts=ocr_texts,
        component_candidates=candidates,
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
                    "component_type": str(item.get("component_type") or item.get("type") or ""),
                    "bbox": _normalize_bbox(item.get("bbox")),
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


def _normalize_ocr_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        normalized = _normalize_ocr_item(item)
        if normalized:
            items.append(normalized)
    return items


def _normalize_ocr_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    text = str(item.get("text") or "").strip()
    if not text:
        return None
    try:
        x1 = float(item.get("x1"))
        y1 = float(item.get("y1"))
        x2 = float(item.get("x2"))
        y2 = float(item.get("y2"))
    except Exception:
        return None
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return {
        **item,
        "text": text,
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
        "cx": (x1 + x2) / 2,
        "cy": (y1 + y2) / 2,
    }


def _split_line_by_gap(line: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if not line:
        return []
    widths = [max(1.0, item["x2"] - item["x1"]) for item in line]
    threshold = max(32.0, statistics.median(widths) * 2.8)
    groups = [[line[0]]]
    for previous, item in zip(line, line[1:]):
        gap = item["x1"] - previous["x2"]
        if gap > threshold:
            groups.append([item])
        else:
            groups[-1].append(item)
    return groups


def _bbox_for_items(items: list[dict[str, Any]]) -> dict[str, float]:
    image_width = max([float(item.get("image_width") or 0) for item in items] or [0])
    image_height = max([float(item.get("image_height") or 0) for item in items] or [0])
    raw = {
        "x1": min(item["x1"] for item in items),
        "y1": min(item["y1"] for item in items),
        "x2": max(item["x2"] for item in items),
        "y2": max(item["y2"] for item in items),
    }
    if image_width > 1 and image_height > 1:
        return {
            "x1": _safe_ratio(raw["x1"] / image_width, 0.0),
            "y1": _safe_ratio(raw["y1"] / image_height, 0.0),
            "x2": _safe_ratio(raw["x2"] / image_width, 1.0),
            "y2": _safe_ratio(raw["y2"] / image_height, 1.0),
        }
    return {
        "x1": _safe_ratio(raw["x1"], 0.0),
        "y1": _safe_ratio(raw["y1"], 0.0),
        "x2": _safe_ratio(raw["x2"], 1.0),
        "y2": _safe_ratio(raw["y2"], 1.0),
    }


def _component_type_hint(texts: list[str], bbox: dict[str, float]) -> str:
    joined = " ".join(texts).lower()
    if any(token in joined for token in ("검색", "조회", "초기화", "search", "filter")) and len(texts) >= 2:
        return "search_filter"
    if any(token in joined for token in ("저장", "등록", "삭제", "수정", "승인", "실행", "업로드", "다운로드", "로그인", "버튼", "button")) and len(texts) <= 4:
        return "button"
    if any(token in joined for token in ("명", "일자", "상태", "구분", "번호", "담당", "제목")) and len(texts) >= 3:
        return "table"
    if any(token in joined for token in ("메뉴", "대시보드", "관리", "설정")) and bbox["x1"] < 0.25:
        return "menu"
    if len(texts) >= 4:
        return "content"
    return "unknown"


def _component_name_from_texts(texts: list[str], component_type: str) -> str:
    compact = [text for text in texts if len(text) <= 24]
    head = " ".join(compact[:4]).strip()
    if head:
        return head
    return {
        "button": "버튼",
        "search_filter": "검색 조건",
        "table": "목록",
        "menu": "메뉴",
        "content": "콘텐츠",
    }.get(component_type, "화면 요소")


def _merge_related_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not candidates:
        return []
    merged: list[dict[str, Any]] = []
    for candidate in candidates:
        if merged and candidate["component_type"] == merged[-1]["component_type"] == "search_filter":
            previous = merged[-1]
            previous["texts"] = [*previous["texts"], *candidate["texts"]]
            previous["bbox"] = _merge_bbox(previous["bbox"], candidate["bbox"])
            previous["component_name"] = _component_name_from_texts(previous["texts"], "search_filter")
            previous["x_ratio"] = (previous["bbox"]["x1"] + previous["bbox"]["x2"]) / 2
            previous["y_ratio"] = (previous["bbox"]["y1"] + previous["bbox"]["y2"]) / 2
            continue
        merged.append(candidate)
    return merged


def _merge_bbox(first: dict[str, float], second: dict[str, float]) -> dict[str, float]:
    return {
        "x1": min(first["x1"], second["x1"]),
        "y1": min(first["y1"], second["y1"]),
        "x2": max(first["x2"], second["x2"]),
        "y2": max(first["y2"], second["y2"]),
    }


def _normalize_component_candidates(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    candidates = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            continue
        texts = _string_list(item.get("texts")) or _string_list(item.get("visible_texts"))
        name = str(item.get("component_name") or item.get("name") or item.get("title") or "").strip()
        bbox = _normalize_bbox(item.get("bbox"))
        x_ratio = _safe_ratio(item.get("x_ratio"), (bbox or {}).get("x1", 0.5))
        y_ratio = _safe_ratio(item.get("y_ratio"), (bbox or {}).get("y1", 0.5))
        candidates.append(
            {
                "candidate_id": str(item.get("candidate_id") or f"CMP-{index:03d}"),
                "component_name": name or _component_name_from_texts(texts, str(item.get("component_type") or "unknown")),
                "component_type": str(item.get("component_type") or item.get("type") or "unknown"),
                "texts": texts,
                "bbox": bbox,
                "x_ratio": x_ratio,
                "y_ratio": y_ratio,
                "reason": str(item.get("reason") or item.get("layout_hint") or ""),
            }
        )
    return candidates


def _normalize_bbox(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    try:
        x1 = float(value.get("x1"))
        y1 = float(value.get("y1"))
        x2 = float(value.get("x2"))
        y2 = float(value.get("y2"))
    except Exception:
        return {}
    return {
        "x1": _safe_ratio(min(x1, x2), 0.0),
        "y1": _safe_ratio(min(y1, y2), 0.0),
        "x2": _safe_ratio(max(x1, x2), 1.0),
        "y2": _safe_ratio(max(y1, y2), 1.0),
    }


def _functional_areas_from_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    areas = []
    for index, candidate in enumerate(candidates, start=1):
        name = str(candidate.get("component_name") or f"컴포넌트 {index}")
        texts = _string_list(candidate.get("texts"))
        areas.append(
            {
                "name": name,
                "visible_texts": texts,
                "area_role": _area_role_from_candidate(candidate),
                "component_type": str(candidate.get("component_type") or "unknown"),
                "bbox": candidate.get("bbox") or {},
                "x_ratio": _safe_ratio(candidate.get("x_ratio"), 0.5),
                "y_ratio": _safe_ratio(candidate.get("y_ratio"), 0.5),
            }
        )
    return areas


def _area_role_from_candidate(candidate: dict[str, Any]) -> str:
    component_type = str(candidate.get("component_type") or "unknown")
    name = str(candidate.get("component_name") or "해당 영역")
    return {
        "button": f"{name} 조작을 실행하는 요소입니다.",
        "input": f"{name} 값을 입력하거나 선택하는 요소입니다.",
        "search_filter": f"{name} 조건을 기준으로 화면 정보를 필터링하는 영역입니다.",
        "table": f"{name} 정보를 행과 열로 확인하는 목록 영역입니다.",
        "card": f"{name} 정보를 요약하여 확인하는 카드 영역입니다.",
        "menu": f"{name} 기능으로 이동하는 내비게이션 영역입니다.",
        "form": f"{name} 정보를 입력하고 검증하는 서식 영역입니다.",
        "chart": f"{name} 현황을 시각적으로 확인하는 영역입니다.",
    }.get(component_type, f"{name} 화면 요소를 확인하고 관련 업무를 수행하는 영역입니다.")


def _screen_name_from_candidates(candidates: list[dict[str, Any]]) -> str:
    for candidate in candidates:
        texts = _string_list(candidate.get("texts"))
        for text in texts:
            if 3 <= len(text) <= 40:
                return text
    return ""
