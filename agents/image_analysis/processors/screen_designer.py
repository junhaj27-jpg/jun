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
      "requirement_basis": "string",
      "component_id": "string",
      "component_bbox": {"x1": "number", "y1": "number", "x2": "number", "y2": "number"}
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
- component_candidates는 이미 의미 검증된 UI 후보만 제공된다. OCR 원문 조각을 처리내용 제목으로 사용하지 마라.
- 처리내용은 component_type이 unknown인 후보, 단일 문자 후보, 깨진 OCR 조각, 숫자/기호 중심 후보를 제외하고 작성하라.
- process_contents는 기능 영역별로 작성하고, title/description/requirement_basis를 서로 다르게 구체화하라.
- description에는 사용자가 해당 영역을 조회, 선택, 입력, 실행했을 때 시스템이 수행하는 처리를 한두 문장으로 작성하라.
- requirement_basis에는 근거가 된 requirement_id와 requirement_name을 포함하라.
- 같은 화면명만 반복하거나, title/description/requirement_basis를 같은 문장으로 채우지 마라.
- process_contents의 no와 button_markers의 no는 반드시 1:1로 일치시켜라.
- 번호 버튼은 대상 component_bbox의 좌측 상단 기준으로 배치하라.
- component_bbox와 button_markers의 x_ratio, y_ratio는 반드시 0~1 상대 좌표로 작성하라.
- 프로토타입 이미지에 없는 업무를 과도하게 만들지 마라.
- 처리내용은 화면 복잡도에 따라 4~8개를 목표로 하되, 실제 기능 영역이 적으면 더 적어도 된다.

[이미지 파일명]
{image_name}

[UI 관찰 결과]
{ui_observation}

[컴포넌트 후보]
{component_candidates}

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

    process_contents = _attach_component_metadata(
        _normalize_process_contents(item.get("process_contents")),
        _component_candidates(analysis),
    )
    if len(process_contents) < 2:
        process_contents = build_process_from_observation(analysis, related_items)
    item["process_contents"] = _enhance_process_contents(
        _renumber(process_contents),
        related_items,
        _component_candidates(analysis),
    )
    item["process_contents"] = _ensure_minimum_process_contents(item["process_contents"], related_items, minimum=2)
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
    if _component_candidates(spec.get("analysis") if isinstance(spec.get("analysis"), dict) else {}):
        missing_bbox = [
            str(item.get("no") or index)
            for index, item in enumerate(process_contents, start=1)
            if isinstance(item, dict) and not item.get("component_bbox")
        ]
        if missing_bbox:
            issues.append("컴포넌트 좌표가 없는 처리내용이 있습니다.")
    return issues


def build_process_from_observation(
    analysis: dict[str, Any],
    related_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """UI 관찰 결과 기반으로 처리내용을 구체화합니다."""

    components = _component_candidates(analysis)
    if components:
        return _build_process_from_components(components, related_items)

    areas = _semantic_areas(analysis.get("functional_areas", []) if isinstance(analysis.get("functional_areas"), list) else [])
    visible_texts = _clean_visible_texts([str(value).strip() for value in analysis.get("visible_texts", []) or [] if str(value).strip()])
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
                "component_id": str(area.get("candidate_id") or area.get("component_id") or ""),
                "component_bbox": area.get("bbox") if isinstance(area.get("bbox"), dict) else {},
            }
        )

    if items:
        return items

    requirement_processes = _build_process_from_requirements(related_items)
    if requirement_processes:
        return requirement_processes

    fallback_names = visible_texts[:4] or _analysis_names(analysis) or ["화면 정보 확인"]
    for index, title in enumerate(fallback_names, start=1):
        basis = _format_requirement_basis(related_items[(index - 1) % len(related_items)]) if related_items else "관련 요구사항"
        items.append(
            {
                "no": index,
                "title": title,
                "description": f"{title} 항목을 기준으로 사용자가 화면 정보를 확인하고 필요한 업무 처리를 수행합니다.",
                "requirement_basis": basis,
                "component_id": "",
                "component_bbox": {},
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
        process_bbox = process.get("component_bbox") if isinstance(process.get("component_bbox"), dict) else {}
        area_bbox = area.get("bbox") if isinstance(area.get("bbox"), dict) else {}
        bbox = process_bbox or area_bbox
        if not bbox:
            continue
        default_x = 0.12 + ((index - 1) % 3) * 0.36
        default_y = 0.18 + min(index - 1, 6) * 0.11
        markers.append(
            {
                "no": index,
                "target_area": str((marker or {}).get("target_area") or area.get("name") or process.get("title") or f"기능 영역 {index}"),
                "x_ratio": _safe_ratio(_bbox_marker_x(bbox, (marker or {}).get("x_ratio", area.get("x_ratio", default_x))), default_x),
                "y_ratio": _safe_ratio(_bbox_marker_y(bbox, (marker or {}).get("y_ratio", area.get("y_ratio", default_y))), default_y),
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
        .replace("{component_candidates}", json.dumps(_component_candidates(analysis), ensure_ascii=False, indent=2)[:5000])
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
        for area in _semantic_areas(analysis.get("functional_areas", []) or [])
        if str(area.get("name") or "").strip()
    ]
    if not areas:
        areas = [str(component.get("component_name") or "").strip() for component in _component_candidates(analysis)[:4]]
    areas = _dedupe_texts([area for area in areas if area])
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
                "component_id": str(item.get("component_id") or item.get("candidate_id") or "").strip(),
                "component_bbox": item.get("component_bbox") if isinstance(item.get("component_bbox"), dict) else {},
            }
        )
    return normalized


def _renumber(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**item, "no": index} for index, item in enumerate(items, start=1)]


def _requirement_process_title(item: dict[str, Any], index: int) -> str:
    text = _normalize_match_text(
        [
            item.get("requirement_name"),
            item.get("req_name"),
            item.get("screen_name"),
            item.get("description"),
            item.get("detail_text"),
        ]
    )
    rules = (
        (("보안", "권한", "인증", "비밀번호", "접근", "잠금", "감사", "로그"), "보안 정책 적용"),
        (("대시보드", "시각화", "추이", "현황", "통계", "리포트"), "운영 현황 제공"),
        (("검색", "조회", "필터", "qa", "질의"), "검색 및 조회 지원"),
        (("문서", "rag", "drm", "업로드", "파일"), "문서 처리 지원"),
        (("agent", "워크플로", "builder", "캔버스"), "Agent 업무 구성"),
        (("모델", "llm", "mlops", "학습", "서빙", "프롬프트"), "모델 운영 관리"),
        (("연계", "api", "sso", "erp", "인터페이스"), "연계 정보 제공"),
        (("채팅", "상담", "대화", "챗봇"), "대화형 업무 지원"),
    )
    for tokens, title in rules:
        if any(token in text for token in tokens):
            return title
    return f"요구사항 기반 처리 {index}"


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


def _component_candidates(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = analysis.get("component_candidates")
    if isinstance(candidates, list) and candidates:
        return [_clean_component(item) for item in candidates if isinstance(item, dict) and _is_process_component(item)]
    areas = analysis.get("functional_areas")
    if not isinstance(areas, list):
        return []
    normalized = []
    for index, area in enumerate(areas, start=1):
        if not isinstance(area, dict):
            continue
        candidate = {
            "candidate_id": str(area.get("candidate_id") or area.get("component_id") or f"AREA-{index:03d}"),
            "component_name": str(area.get("component_name") or area.get("name") or f"기능 영역 {index}"),
            "component_type": str(area.get("component_type") or area.get("type") or "unknown"),
            "texts": area.get("visible_texts") if isinstance(area.get("visible_texts"), list) else [],
            "bbox": area.get("bbox") if isinstance(area.get("bbox"), dict) else {},
            "x_ratio": area.get("x_ratio"),
            "y_ratio": area.get("y_ratio"),
        }
        if _is_process_component(candidate):
            normalized.append(_clean_component(candidate))
    return normalized


def _build_process_from_components(
    components: list[dict[str, Any]],
    related_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items = []
    ranked_components = _rank_components_for_process(components)
    for index, component in enumerate(ranked_components, start=1):
        title = _component_title(component, index)
        related_item = _select_requirement_for_component(component, related_items, index)
        basis = _format_requirement_basis(related_item) if related_item else "관련 요구사항"
        items.append(
            {
                "no": index,
                "title": title,
                "description": _component_description(component, title, related_item),
                "requirement_basis": basis,
                "component_id": str(component.get("candidate_id") or ""),
                "component_bbox": component.get("bbox") if isinstance(component.get("bbox"), dict) else {},
            }
        )
    return items


def _build_process_from_requirements(related_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for index, requirement in enumerate(related_items[:3], start=1):
        title = _requirement_process_title(requirement, index)
        if not title:
            continue
        items.append(
            {
                "no": index,
                "title": title,
                "description": _requirement_context_sentence(requirement) or f"{title} 요구사항을 기준으로 화면에서 필요한 정보를 제공하고 업무 처리를 지원합니다.",
                "requirement_basis": _format_requirement_basis(requirement),
                "component_id": "",
                "component_bbox": {},
                "marker_excluded": True,
            }
        )
    return items


def _enhance_process_contents(
    process_contents: list[dict[str, Any]],
    related_items: list[dict[str, Any]],
    components: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not process_contents:
        return process_contents
    enhanced = []
    for index, process in enumerate(process_contents, start=1):
        item = dict(process)
        component = _find_component_for_process(item, components) if components else None
        related_item = _select_requirement_for_component(component or item, related_items, index)
        current = str(item.get("description") or "").strip()
        if _description_needs_enrichment(current):
            title = str(item.get("title") or "").strip()
            item["description"] = _component_description(component or item, title, related_item)
        elif related_item and not _mentions_requirement_context(current, related_item):
            item["description"] = current + " " + _requirement_context_sentence(related_item)
        if not str(item.get("requirement_basis") or "").strip() and related_item:
            item["requirement_basis"] = _format_requirement_basis(related_item)
        enhanced.append(item)
    return enhanced


def _ensure_minimum_process_contents(
    process_contents: list[dict[str, Any]],
    related_items: list[dict[str, Any]],
    *,
    minimum: int,
) -> list[dict[str, Any]]:
    if len(process_contents) >= minimum or not related_items:
        return process_contents
    existing_titles = {str(item.get("title") or "").strip() for item in process_contents}
    output = [dict(item) for item in process_contents]
    for requirement in related_items:
        if len(output) >= minimum:
            break
        title = _requirement_process_title(requirement, len(output) + 1)
        if not title or title in existing_titles:
            continue
        output.append(
            {
                "no": len(output) + 1,
                "title": title,
                "description": _requirement_context_sentence(requirement) or f"{title} 요구사항을 기준으로 화면에서 필요한 정보를 제공하고 업무 처리를 지원합니다.",
                "requirement_basis": _format_requirement_basis(requirement),
                "component_id": "",
                "component_bbox": {},
                "marker_excluded": True,
            }
        )
        existing_titles.add(title)
    return _renumber(output)


def _attach_component_metadata(
    process_contents: list[dict[str, Any]],
    components: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not process_contents or not components:
        return process_contents
    by_id = {str(item.get("candidate_id") or ""): item for item in components if isinstance(item, dict)}
    enriched = []
    for process in process_contents:
        item = dict(process)
        component = by_id.get(str(item.get("component_id") or ""))
        if component is None:
            component = _find_component_for_process(item, components)
        if component is not None:
            item.setdefault("component_id", str(component.get("candidate_id") or ""))
            if not item.get("component_bbox") and isinstance(component.get("bbox"), dict):
                item["component_bbox"] = component["bbox"]
        enriched.append(item)
    return enriched


def _find_component_for_process(
    process: dict[str, Any],
    components: list[dict[str, Any]],
) -> dict[str, Any] | None:
    title = _normalize_match_text(process.get("title"))
    description = _normalize_match_text(process.get("description"))
    best: tuple[int, dict[str, Any]] | None = None
    for component in components:
        component_text = _normalize_match_text(
            [
                component.get("component_name"),
                component.get("texts"),
                component.get("component_type"),
            ]
        )
        score = 0
        for token in _match_tokens(title):
            if token in component_text:
                score += 3
        for token in _match_tokens(description):
            if token in component_text:
                score += 1
        if score and (best is None or score > best[0]):
            best = (score, component)
    return best[1] if best else None


def _rank_components_for_process(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    meaningful = []
    for component in components:
        if not _is_process_component(component):
            continue
        meaningful.append(_clean_component(component))
    meaningful.sort(
        key=lambda item: (
            _component_priority(str(item.get("component_type") or "")),
            float(item.get("y_ratio") or 0.5),
            float(item.get("x_ratio") or 0.5),
        )
    )
    return meaningful[:8]


def _component_priority(component_type: str) -> int:
    order = {
        "search_filter": 1,
        "form": 2,
        "input": 2,
        "table": 3,
        "card": 4,
        "chart": 4,
        "button": 5,
        "menu": 6,
        "content": 7,
    }
    return order.get(component_type, 9)


def _select_requirement_for_component(
    component: dict[str, Any] | None,
    related_items: list[dict[str, Any]],
    index: int,
) -> dict[str, Any] | None:
    if not related_items:
        return None
    if not component:
        return related_items[(index - 1) % len(related_items)]
    component_terms = set(_match_tokens([
        component.get("component_name"),
        component.get("title"),
        component.get("texts"),
        component.get("description"),
    ]))
    best: tuple[int, int, dict[str, Any]] | None = None
    for order, item in enumerate(related_items):
        item_terms = set(_match_tokens(_compact_source_item(item)))
        score = len(component_terms & item_terms) * 4
        compact = _normalize_match_text(_compact_source_item(item))
        for term in component_terms:
            if term and term in compact:
                score += 1
        if best is None or score > best[0]:
            best = (score, -order, item)
    if best and best[0] > 0:
        return best[2]
    return related_items[(index - 1) % len(related_items)]


def _description_needs_enrichment(description: str) -> bool:
    if len(description) < 80:
        return True
    generic_phrases = (
        "화면 정보를 확인하고 관련 업무를 수행",
        "관련 업무 처리를 실행",
        "카드 형태로 제공합니다",
        "시각적으로 제공합니다",
    )
    return any(phrase in description for phrase in generic_phrases) and "요구사항" not in description


def _mentions_requirement_context(description: str, related_item: dict[str, Any]) -> bool:
    req_name = str(related_item.get("requirement_name") or related_item.get("req_name") or "").strip()
    return bool(req_name and req_name in description)


def _requirement_context_sentence(related_item: dict[str, Any] | None) -> str:
    if not related_item:
        return ""
    req_name = str(related_item.get("requirement_name") or related_item.get("req_name") or "").strip()
    detail = _first_meaningful_text(
        related_item.get("description"),
        related_item.get("detail_text"),
        *((related_item.get("constraints") or [])[:2] if isinstance(related_item.get("constraints"), list) else []),
        *((related_item.get("validation_criteria") or [])[:2] if isinstance(related_item.get("validation_criteria"), list) else []),
    )
    if req_name and detail:
        return f"이는 '{req_name}' 요구사항에 따라 {detail}"
    if req_name:
        return f"이는 '{req_name}' 요구사항을 지원하기 위한 처리입니다."
    if detail:
        return detail
    return ""


def _first_meaningful_text(*values: Any) -> str:
    for value in values:
        text = _clean_sentence(value)
        if text:
            return text
    return ""


def _clean_sentence(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    text = _trim_sentence(text, max_length=150)
    if text[-1] not in ".다요":
        text += "."
    return text


def _trim_sentence(text: str, *, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    for marker in ("다.", "요.", ". ", ", ", "·", "; "):
        pos = text.rfind(marker, 0, max_length)
        if pos >= max_length * 0.55:
            return text[: pos + len(marker)].rstrip(" ,;·")
    return text[:max_length].rstrip(" ,;·")


def _normalize_match_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(_normalize_match_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_normalize_match_text(item) for item in value.values())
    return str(value).lower()


def _match_tokens(value: Any) -> list[str]:
    stopwords = {
        "화면",
        "영역",
        "사용자",
        "시스템",
        "업무",
        "처리",
        "정보",
        "확인",
        "관련",
        "요소",
    }
    return [
        token
        for token in re.findall(r"[가-힣A-Za-z0-9_]{2,}", _normalize_match_text(value))
        if token not in stopwords
    ]


def _component_title(component: dict[str, Any], index: int) -> str:
    name = _clean_text(component.get("component_name"))
    if name:
        return name
    texts = _clean_visible_texts([str(value).strip() for value in component.get("texts", []) or [] if str(value).strip()])
    return " ".join(texts[:4]) or f"화면 요소 {index}"


def _component_description(
    component: dict[str, Any],
    title: str,
    related_item: dict[str, Any] | None = None,
) -> str:
    component_type = str(component.get("component_type") or "unknown")
    texts = _clean_visible_texts([str(value).strip() for value in component.get("texts", []) or [] if str(value).strip()])
    text_clause = f" 화면에는 {', '.join(texts[:8])} 항목이 표시됩니다." if texts else ""
    base = {
        "button": f"사용자가 {title} 요소를 선택하면 시스템은 화면 상태와 입력값을 확인한 뒤 해당 업무 처리를 실행합니다.",
        "input": f"사용자가 {title} 항목에 값을 입력하거나 선택하면 시스템은 입력값을 후속 조회, 검증, 처리 조건으로 활용합니다.",
        "search_filter": f"사용자가 {title} 영역에서 조건을 입력하고 조회하면 시스템은 조건에 맞는 대상 정보를 선별하여 결과 영역에 반영합니다.",
        "table": f"시스템은 {title} 영역에서 업무 대상 정보를 행과 열 구조로 제공하고, 사용자가 항목의 상태와 세부 내용을 비교해 선택할 수 있도록 합니다.",
        "card": f"시스템은 {title} 영역에서 핵심 현황과 요약 지표를 카드 형태로 제공하고, 사용자가 현재 상태를 빠르게 판단할 수 있도록 합니다.",
        "menu": f"사용자가 {title} 항목을 선택하면 시스템은 관련 업무 화면으로 이동하거나 해당 기능 영역을 활성화합니다.",
        "form": f"사용자가 {title} 영역에서 업무 정보를 입력하면 시스템은 필수값, 형식, 처리 가능 여부를 확인해 다음 단계로 전달합니다.",
        "chart": f"시스템은 {title} 영역에서 업무 현황과 추이를 시각화하고, 사용자가 기간별 변화와 이상 징후를 파악할 수 있도록 합니다.",
    }.get(component_type, f"사용자는 {title} 영역에서 화면 정보를 확인하고 관련 업무를 수행하며, 시스템은 선택된 항목에 맞는 후속 처리를 지원합니다.")
    requirement_clause = _requirement_context_sentence(related_item) if related_item else ""
    return " ".join(part for part in (base, text_clause, requirement_clause) if part).strip()


def _bbox_marker_x(bbox: dict[str, Any], default: Any) -> Any:
    try:
        x1 = float(bbox.get("x1"))
        x2 = float(bbox.get("x2"))
        return min(0.97, max(0.03, (x1 + 0.024) if x2 > x1 else (x1 + x2) / 2))
    except Exception:
        return default


def _bbox_marker_y(bbox: dict[str, Any], default: Any) -> Any:
    try:
        y1 = float(bbox.get("y1"))
        y2 = float(bbox.get("y2"))
        return min(0.97, max(0.03, (y1 + 0.024) if y2 > y1 else (y1 + y2) / 2))
    except Exception:
        return default


def _semantic_areas(areas: list[Any]) -> list[dict[str, Any]]:
    semantic = []
    for area in areas:
        if not isinstance(area, dict):
            continue
        name = _clean_text(area.get("name") or area.get("title"))
        component_type = str(area.get("component_type") or area.get("type") or "unknown").lower()
        texts = _clean_visible_texts([str(value) for value in area.get("visible_texts", []) or []])
        if component_type == "unknown" or not name or _looks_like_file_stem(name):
            continue
        if _is_brand_component(area, name, texts) or _is_generic_ui_word(name):
            continue
        if _noise_ratio(" ".join([name, *texts])) > 0.35:
            continue
        semantic.append({**area, "name": name, "visible_texts": texts})
    return semantic


def _is_process_component(component: dict[str, Any]) -> bool:
    component_type = str(component.get("component_type") or "unknown").strip().lower()
    if component_type in {"unknown", "menu"}:
        return False
    name = _clean_text(component.get("component_name") or component.get("name"))
    texts = _clean_visible_texts([str(value) for value in component.get("texts", []) or []])
    if _is_brand_component(component, name, texts) or _is_global_header_component(component, name, texts) or _is_generic_ui_word(name):
        return False
    bbox = component.get("bbox") if isinstance(component.get("bbox"), dict) else {}
    try:
        y1 = float(bbox.get("y1", 1.0) or 1.0)
        x1 = float(bbox.get("x1", 1.0) or 1.0)
    except Exception:
        y1 = 1.0
        x1 = 1.0
    if y1 < 0.17 and component_type not in {"search_filter", "button", "input"}:
        return False
    if x1 < 0.2 and component_type not in {"search_filter", "button", "input", "card"}:
        return False
    joined = " ".join([name, *texts]).strip()
    if not joined or _looks_like_file_stem(joined) or _noise_ratio(joined) > 0.35:
        return False
    if component_type == "content" and len(texts) < 2 and len(name) < 3:
        return False
    return True


def _clean_component(component: dict[str, Any]) -> dict[str, Any]:
    return {
        **component,
        "component_name": _clean_text(component.get("component_name") or component.get("name")),
        "texts": _clean_visible_texts([str(value) for value in component.get("texts", []) or []]),
    }


def _is_global_header_component(component: dict[str, Any], name: str, texts: list[str]) -> bool:
    bbox = component.get("bbox") if isinstance(component.get("bbox"), dict) else {}
    try:
        x1 = float(bbox.get("x1", 1.0) or 1.0)
        y1 = float(bbox.get("y1", 1.0) or 1.0)
        x2 = float(bbox.get("x2", 0.0) or 0.0)
    except Exception:
        return False
    joined = " ".join([name, *texts]).lower()
    header_tokens = ("통합 검색", "검색", "권한", "kms", "전략부", "부서", "로그인")
    return y1 < 0.14 and x1 > 0.58 and any(token in joined for token in header_tokens)


def _clean_visible_texts(values: list[str]) -> list[str]:
    cleaned = []
    seen: set[str] = set()
    for value in values:
        text = _clean_text(value)
        if not text or text in seen or not _is_usable_text(text):
            continue
        seen.add(text)
        cleaned.append(text)
    return cleaned


def _dedupe_texts(values: list[str]) -> list[str]:
    deduped = []
    seen: set[str] = set()
    for value in values:
        text = _clean_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def _clean_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    text = text.replace("아시 Platform", "AI Platform")
    text = re.sub(r"\bSaori\b", "AI", text, flags=re.IGNORECASE)
    text = re.sub(r"SQL[- ]?Pytho\b", "SQL-Python", text, flags=re.IGNORECASE)
    return text.strip(" \t\r\n.,;:|/\\[]{}()<>")


def _is_usable_text(text: str) -> bool:
    text = _clean_text(text)
    if _looks_like_file_stem(text):
        return False
    if len(text) == 1 and text not in {"홈"}:
        return False
    if re.fullmatch(r"[\W_]+", text) or re.fullmatch(r"[\d\s%.,:-]+", text):
        return False
    if not re.search(r"[가-힣A-Za-z]", text):
        return False
    if len(text) <= 3 and re.fullmatch(r"[A-Za-z]{1,3}", text):
        return text.lower() in {"ai", "id", "api", "sql"}
    if _is_generic_ui_word(text):
        return False
    return True


def _looks_like_file_stem(text: str) -> bool:
    return bool(re.match(r"^\d{1,3}[_-][가-힣A-Za-z0-9_ -]+$", _clean_text(text)))


def _noise_ratio(text: str) -> float:
    if not text:
        return 1.0
    noisy = len(re.findall(r"[^가-힣A-Za-z0-9\s]", text))
    return noisy / max(1, len(text))


def _is_brand_component(component: dict[str, Any], name: str, texts: list[str]) -> bool:
    joined = " ".join([name, *texts]).strip().lower()
    bbox = component.get("bbox") if isinstance(component.get("bbox"), dict) else {}
    x1 = float(bbox.get("x1", 1.0) or 1.0)
    y1 = float(bbox.get("y1", 1.0) or 1.0)
    if any(token in joined for token in ("sf ai platform", "ai platform", "on-premise genai portal")) and x1 < 0.25 and y1 < 0.2:
        return True
    return joined in {"ai platform", "sf ai platform"}


def _is_generic_ui_word(text: str) -> bool:
    return _clean_text(text).lower() in {
        "서비스",
        "부서별",
        "문서",
        "사용자",
        "관리",
        "정보",
        "상태",
        "플랫폼",
        "platform",
    }
