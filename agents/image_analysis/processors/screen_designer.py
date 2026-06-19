"""인터페이스 화면 상세 설계 JSON을 생성하고 품질을 보강합니다."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import re
from typing import Any

from agents.image_analysis.processors.image_analyzer import build_vision_content
from tools.llm.llm_client import LLMClient
from tools.llm.response_parser import parse_json_response


SCREEN_DETAIL_PROMPT = """
너는 공공기관 정보시스템의 사용자 인터페이스 설계서를 작성하는 UI/UX 분석 Agent다.

아래에는 현재 프로토타입 이미지에서 추출한 UI 관찰 결과와, 그 화면과 관련성이 높은 사용자 요구사항만 선별한 목록이 있다.
현재 이미지를 다시 확인하면서 화면설계서의 "3. 화면 상세 설계"에 들어갈 기본정보와 처리 내용을 생성하라.

반드시 JSON으로만 출력하라. 마크다운 금지.

출력 JSON schema:
{
  "screen_id": "string",
  "screen_name": "string",
  "screen_type": "string",
  "menu_path": "string",
  "screen_overview": "string",
  "process_contents": [
    {
      "no": "number",
      "title": "string",
      "description": "string",
      "requirement_basis": "string"
    }
  ],
  "button_markers": [
    {
      "no": "number",
      "target_area": "string",
      "x_ratio": "number",
      "y_ratio": "number"
    }
  ]
}

작성 규칙:
- 관련 유스케이스 ID, 관련 시퀀스도 ID는 절대 생성하지 말고 JSON에도 포함하지 마라.
- 화면명은 이미지 제목, 메뉴, 파일명 맥락 중 가장 구체적인 이름으로 작성하라.
- 처리내용은 반드시 화면에 실제로 보이는 UI 영역 하나와 사용자 요구사항 하나 이상을 연결해서 작성하라.
- process_contents는 기능 영역별로 작성하고, title/description/requirement_basis를 서로 다르게 구체화하라.
- description에는 사용자가 해당 영역을 조회, 선택, 입력, 실행했을 때 시스템이 수행하는 처리를 한두 문장으로 작성하라.
- requirement_basis에는 근거가 된 requirement_id와 requirement_name을 포함하라.
- 같은 화면명만 반복하거나, title/description/requirement_basis를 같은 문장으로 채우지 마라.
- process_contents의 no와 button_markers의 no는 반드시 1:1로 일치시켜라.
- 번호 버튼은 텍스트를 많이 가리지 않도록 카드 모서리, 영역 외곽, 여백 근처에 배치하라.
- 프로토타입 이미지에 없는 업무를 과도하게 만들지 마라.
- 처리내용은 화면 복잡도에 따라 4~8개를 목표로 하되, 실제 기능 영역이 적으면 더 적어도 된다.

[이미지 파일명]
{image_name}

[UI 관찰 결과]
{ui_observation}

[UIUX Guide RAG Context]
{ui_reference_context}

[선별된 사용자 요구사항]
{related_requirements}
"""


def refine_screen_designs(
    screens: list[dict[str, Any]],
    source_items: list[dict[str, Any]],
    *,
    llm_client: LLMClient | None,
    warnings: list[dict[str, Any]],
    search_contexts: list[dict[str, Any]] | None = None,
    max_workers: int = 4,
) -> list[dict[str, Any]]:
    """화면별 상세 설계를 생성하고 부실한 처리내용을 보강합니다."""

    if not screens:
        return screens

    context_by_id = {
        str(context.get("screen_id")): context
        for context in search_contexts or []
        if isinstance(context, dict)
    }
    if llm_client is None:
        return [
            ensure_screen_design_content(screen, _related_items(screen, source_items))
            for screen in screens
        ]

    refined = [dict(screen) for screen in screens]
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as executor:
        future_map = {
            executor.submit(
                _refine_one_screen,
                screen,
                _related_items(screen, source_items),
                llm_client,
                _ui_reference_context(context_by_id.get(str(screen.get("screen_id")))),
            ): index
            for index, screen in enumerate(refined)
        }
        for future in as_completed(future_map):
            index = future_map[future]
            try:
                refined[index] = future.result()
            except Exception as exc:
                warnings.append(
                    {
                        "code": "INTERFACE_SCREEN_DETAIL_FAILED",
                        "message": str(exc),
                        "screen_id": refined[index].get("screen_id"),
                    }
                )
                refined[index] = ensure_screen_design_content(
                    refined[index],
                    _related_items(refined[index], source_items),
                )
    return refined


def ensure_screen_design_content(
    screen: dict[str, Any],
    related_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """LLM 상세 설계가 빈약해도 문서에 들어갈 필드를 채웁니다."""

    item = dict(screen)
    analysis = item.get("analysis") if isinstance(item.get("analysis"), dict) else {}
    item["screen_name"] = str(
        item.get("screen_name")
        or analysis.get("screen_name_candidate")
        or Path(str(item.get("image_path") or "screen")).stem
    )
    item["screen_type"] = str(item.get("screen_type") or analysis.get("screen_type") or "업무 화면")
    menu_candidates = analysis.get("menu_path_candidates") if isinstance(analysis.get("menu_path_candidates"), list) else []
    item["menu_path"] = str(item.get("menu_path") or (menu_candidates[0] if menu_candidates else item["screen_name"]))
    if not str(item.get("screen_overview") or "").strip():
        item["screen_overview"] = _build_screen_overview(item, analysis, related_items)

    process_contents = _normalize_process_contents(item.get("process_contents"))
    if len(process_contents) < 2:
        process_contents = build_process_from_observation(analysis, related_items)
    item["process_contents"] = _renumber(process_contents)
    item["button_markers"] = build_markers_from_observation(item["process_contents"], analysis, item.get("button_markers"))

    issues = validate_screen_spec_quality(item)
    if issues:
        item["quality_issues"] = issues
    return item


def validate_screen_spec_quality(spec: dict[str, Any]) -> list[str]:
    """반복 출력과 부실한 처리내용을 감지합니다."""

    issues = []
    process_contents = spec.get("process_contents", []) or []
    if len(process_contents) < 3:
        issues.append("처리내용이 3개 미만입니다.")
    titles = [str(item.get("title", "")).strip() for item in process_contents if isinstance(item, dict)]
    descriptions = [str(item.get("description", "")).strip() for item in process_contents if isinstance(item, dict)]
    bases = [str(item.get("requirement_basis", "")).strip() for item in process_contents if isinstance(item, dict)]
    screen_name = str(spec.get("screen_name", "")).strip()
    if len(process_contents) >= 3 and titles and len(set(titles)) <= max(1, len(titles) // 3):
        issues.append("처리내용 제목 반복이 많습니다.")
    if len(process_contents) >= 3 and descriptions and len(set(descriptions)) <= max(1, len(descriptions) // 3):
        issues.append("처리내용 설명 반복이 많습니다.")
    if bases and len(process_contents) >= 3 and len(set(bases)) <= max(1, len(bases) // 3):
        issues.append("요구사항 근거 반복이 많습니다.")
    if sum(1 for value in titles + descriptions + bases if value == screen_name) >= max(2, len(process_contents)):
        issues.append("화면명만 반복된 항목이 많습니다.")
    if descriptions and sum(1 for value in descriptions if len(value) < 18) >= max(1, len(descriptions) // 2):
        issues.append("처리내용 설명이 너무 짧습니다.")
    marker_nos = {
        int(marker.get("no"))
        for marker in spec.get("button_markers", []) or []
        if isinstance(marker, dict) and str(marker.get("no", "")).isdigit()
    }
    process_nos = {
        int(item.get("no"))
        for item in process_contents
        if isinstance(item, dict) and str(item.get("no", "")).isdigit()
    }
    if process_nos != marker_nos:
        issues.append("처리내용 번호와 버튼 번호가 일치하지 않습니다.")
    return issues


def build_process_from_observation(
    analysis: dict[str, Any],
    related_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """UI 관찰 결과 기반으로 처리내용을 구체화합니다."""

    areas = analysis.get("functional_areas", []) if isinstance(analysis.get("functional_areas"), list) else []
    visible_texts = [str(value).strip() for value in analysis.get("visible_texts", []) or [] if str(value).strip()]
    items = []

    for index, area in enumerate(areas, start=1):
        if not isinstance(area, dict):
            continue
        title = str(area.get("name") or f"기능 영역 {index}").strip()
        role = str(area.get("area_role") or "").strip()
        texts = [str(value).strip() for value in area.get("visible_texts", []) or [] if str(value).strip()]
        basis = _format_requirement_basis(related_items[(index - 1) % len(related_items)]) if related_items else "관련 요구사항"
        description = role or f"{title} 영역에서 사용자가 필요한 정보를 확인하고 업무 처리를 수행합니다."
        if texts:
            description += " 표시 텍스트: " + ", ".join(texts[:5])
        items.append(
            {
                "no": index,
                "title": title,
                "description": description,
                "requirement_basis": basis,
            }
        )

    if items:
        return items

    fallback_names = visible_texts[:6] or _analysis_names(analysis) or ["화면 정보 확인"]
    for index, title in enumerate(fallback_names, start=1):
        basis = _format_requirement_basis(related_items[(index - 1) % len(related_items)]) if related_items else "관련 요구사항"
        items.append(
            {
                "no": index,
                "title": title,
                "description": f"{title} 항목을 기준으로 사용자가 화면 정보를 확인하고 필요한 업무 처리를 수행합니다.",
                "requirement_basis": basis,
            }
        )
    return items


def build_markers_from_observation(
    process_contents: list[dict[str, Any]],
    analysis: dict[str, Any],
    raw_markers: Any = None,
) -> list[dict[str, Any]]:
    """처리내용 번호와 1:1로 맞는 버튼 마커를 구성합니다."""

    marker_by_no = {}
    if isinstance(raw_markers, list):
        for marker in raw_markers:
            if not isinstance(marker, dict):
                continue
            try:
                marker_by_no[int(marker.get("no"))] = marker
            except Exception:
                continue
    areas = analysis.get("functional_areas", []) if isinstance(analysis.get("functional_areas"), list) else []
    markers = []
    for index, process in enumerate(process_contents, start=1):
        marker = marker_by_no.get(index)
        area = areas[index - 1] if index - 1 < len(areas) and isinstance(areas[index - 1], dict) else {}
        default_x = 0.12 + ((index - 1) % 3) * 0.36
        default_y = 0.18 + min(index - 1, 6) * 0.11
        markers.append(
            {
                "no": index,
                "target_area": str((marker or {}).get("target_area") or area.get("name") or process.get("title") or f"기능 영역 {index}"),
                "x_ratio": _safe_ratio((marker or {}).get("x_ratio", area.get("x_ratio", default_x)), default_x),
                "y_ratio": _safe_ratio((marker or {}).get("y_ratio", area.get("y_ratio", default_y)), default_y),
            }
        )
    return markers


def _refine_one_screen(
    screen: dict[str, Any],
    related_items: list[dict[str, Any]],
    llm_client: LLMClient,
    ui_reference_context: str,
) -> dict[str, Any]:
    fallback = ensure_screen_design_content(screen, related_items)
    generated = _generate_detail(screen, related_items, llm_client, ui_reference_context=ui_reference_context, extra_issues=[])
    detail = ensure_screen_design_content({**fallback, **generated}, related_items)
    issues = validate_screen_spec_quality(detail)
    if not issues:
        return detail

    retry = _generate_detail(screen, related_items, llm_client, ui_reference_context=ui_reference_context, extra_issues=issues)
    retry_detail = ensure_screen_design_content({**fallback, **retry}, related_items)
    retry_issues = validate_screen_spec_quality(retry_detail)
    return retry_detail if len(retry_issues) <= len(issues) else detail


def _generate_detail(
    screen: dict[str, Any],
    related_items: list[dict[str, Any]],
    llm_client: LLMClient,
    *,
    ui_reference_context: str,
    extra_issues: list[str],
) -> dict[str, Any]:
    analysis = screen.get("analysis") if isinstance(screen.get("analysis"), dict) else {}
    image_name = Path(str(screen.get("image_path") or "")).name
    prompt = (
        SCREEN_DETAIL_PROMPT.replace("{image_name}", image_name)
        .replace("{ui_observation}", json.dumps(analysis, ensure_ascii=False, indent=2)[:5000])
        .replace("{ui_reference_context}", ui_reference_context[:6000])
        .replace(
            "{related_requirements}",
            json.dumps([_compact_source_item(item) for item in related_items[:10]], ensure_ascii=False, indent=2)[:7000],
        )
    )
    if extra_issues:
        prompt += (
            "\n\n[품질 검증 실패 항목]\n"
            + json.dumps(extra_issues, ensure_ascii=False)
            + "\n위 문제를 반드시 수정해서 JSON만 다시 출력하라."
        )
    warnings: list[dict[str, Any]] = []
    image_path = str(screen.get("image_path") or "")
    content = [
        {
            "type": "text",
            "text": prompt,
        }
    ]
    if image_path:
        content = build_vision_content(image_path, warnings)
        content[0]["text"] = prompt

    result = llm_client.chat(
        [
            {"role": "system", "content": "사용자 인터페이스 화면 상세 설계 JSON만 반환하세요."},
            {"role": "user", "content": content},
        ]
    )
    if not result["success"]:
        return {}
    parsed = parse_json_response(result["data"])
    return parsed["data"] if parsed["success"] and isinstance(parsed["data"], dict) else {}


def _related_items(screen: dict[str, Any], source_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ids = {str(value) for value in screen.get("matched_requirement_ids") or [] if value}
    analysis = screen.get("analysis") if isinstance(screen.get("analysis"), dict) else {}
    image_path = Path(str(screen.get("image_path") or ""))
    if not ids:
        return _select_related_items(source_items, analysis, image_path)
    matched = [
        item for item in source_items
        if str(item.get("requirement_id") or item.get("req_id") or item.get("screen_id") or "") in ids
    ]
    return matched or _select_related_items(source_items, analysis, image_path)


def _compact_source_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "requirement_id": item.get("requirement_id") or item.get("req_id") or item.get("screen_id") or "",
        "requirement_name": item.get("requirement_name") or item.get("req_name") or item.get("screen_name") or "",
        "requirement_type": item.get("requirement_type") or item.get("type") or "",
        "description": str(item.get("description") or item.get("detail_text") or item.get("screen_overview") or "")[:420],
        "constraints": [str(value)[:180] for value in (item.get("constraints") or [])[:3]] if isinstance(item.get("constraints"), list) else [],
        "validation_criteria": [str(value)[:160] for value in (item.get("validation_criteria") or [])[:3]] if isinstance(item.get("validation_criteria"), list) else [],
    }


def _build_screen_overview(
    screen: dict[str, Any],
    analysis: dict[str, Any],
    related_items: list[dict[str, Any]],
) -> str:
    name = str(screen.get("screen_name") or analysis.get("screen_name_candidate") or "해당 화면")
    purpose = str(analysis.get("purpose") or "").strip()
    areas = [
        str(area.get("name") or "").strip()
        for area in analysis.get("functional_areas", []) or []
        if isinstance(area, dict) and str(area.get("name") or "").strip()
    ]
    req_names = [
        str(item.get("requirement_name") or item.get("req_name") or item.get("screen_name") or "").strip()
        for item in related_items[:3]
        if isinstance(item, dict)
    ]
    first = f"{name}은 {purpose}을 위한 화면입니다." if purpose else f"{name}은 사용자가 주요 업무를 처리하기 위한 화면입니다."
    if areas:
        first += " " + ", ".join(areas[:4]) + " 영역을 중심으로 화면을 구성합니다."
    if req_names:
        first += " 관련 요구사항: " + ", ".join(value for value in req_names if value) + "."
    return first


def _select_related_items(
    source_items: list[dict[str, Any]],
    analysis: dict[str, Any],
    image_path: Path,
    limit: int = 10,
) -> list[dict[str, Any]]:
    screen_context = _build_screen_match_context(image_path, analysis)
    screen_terms = set(_extract_match_terms(screen_context))
    scored = []
    for order, item in enumerate(source_items):
        if not isinstance(item, dict):
            continue
        compact = _compact_source_item(item)
        item_text = _normalize_text_for_match(compact)
        item_terms = set(_extract_match_terms(item_text))
        overlap = screen_terms & item_terms
        score = len(overlap) * 3
        for term in screen_terms:
            if term and term in item_text:
                score += 1
        if score > 0:
            selected = dict(item)
            selected["match_score"] = score
            selected["matched_terms"] = sorted(overlap)[:12]
            scored.append((score, -order, selected))
    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [item for _, _, item in scored[:limit]] or [item for item in source_items[:limit] if isinstance(item, dict)]


def _build_screen_match_context(image_path: Path, analysis: dict[str, Any]) -> str:
    parts: list[Any] = [image_path.stem]
    parts.extend(analysis.get("screen_name_candidates", []) or [])
    parts.extend(analysis.get("menu_path_candidates", []) or [])
    parts.extend(analysis.get("visible_texts", []) or [])
    for area in analysis.get("functional_areas", []) or []:
        if not isinstance(area, dict):
            continue
        parts.append(area.get("name", ""))
        parts.append(area.get("area_role", ""))
        parts.extend(area.get("visible_texts", []) or [])
    return _normalize_text_for_match(parts)


def _normalize_text_for_match(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(_normalize_text_for_match(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_normalize_text_for_match(item) for item in value.values())
    return str(value).lower()


def _extract_match_terms(text: str) -> list[str]:
    stopwords = {
        "string",
        "number",
        "null",
        "true",
        "false",
        "화면",
        "사용자",
        "시스템",
        "요구사항",
        "기능",
        "처리",
        "관리",
        "제공",
        "지원",
        "정보",
        "데이터",
        "서비스",
        "설계",
        "구현",
        "확인",
        "조회",
        "입력",
        "출력",
        "목록",
        "상태",
        "결과",
        "내용",
        "기반",
        "관련",
    }
    terms = re.findall(r"[가-힣A-Za-z0-9_]{2,}", text.lower())
    return [term for term in terms if term not in stopwords and len(term) >= 2]


def _ui_reference_context(context: dict[str, Any] | None) -> str:
    if not context:
        return ""
    rows = []
    for key in ("ux_guides", "interface_requirements"):
        values = context.get(key)
        if not isinstance(values, list):
            continue
        for value in values[:5]:
            if isinstance(value, dict):
                rows.append(str(value.get("content") or value.get("title") or value.get("snippet") or value))
            elif value:
                rows.append(str(value))
    return "\n".join(rows)


def _normalize_process_contents(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    normalized = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "no": index,
                "title": str(item.get("title") or item.get("name") or f"처리 {index}").strip(),
                "description": str(item.get("description") or item.get("content") or "").strip(),
                "requirement_basis": str(item.get("requirement_basis") or item.get("basis") or "").strip(),
            }
        )
    return normalized


def _renumber(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**item, "no": index} for index, item in enumerate(items, start=1)]


def _format_requirement_basis(item: dict[str, Any]) -> str:
    req_id = str(item.get("requirement_id") or item.get("req_id") or item.get("screen_id") or "").strip()
    req_name = str(item.get("requirement_name") or item.get("req_name") or item.get("screen_name") or "").strip()
    return f"{req_id} {req_name}".strip() or "관련 요구사항"


def _analysis_names(analysis: dict[str, Any]) -> list[str]:
    values = []
    for key in ("input_fields", "buttons", "user_actions", "navigation_candidates"):
        value = analysis.get(key)
        if isinstance(value, list):
            values.extend(str(item).strip() for item in value if str(item).strip())
    return values


def _safe_ratio(value: Any, default: float) -> float:
    try:
        return max(0.03, min(0.97, float(value)))
    except Exception:
        return default
