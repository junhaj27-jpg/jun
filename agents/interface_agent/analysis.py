from agents.interface_agent.config import *
from agents.interface_agent.model_runtime import qwen_generate_text, qwen_analyze_image, parse_or_repair_json
from generators.interface_image_markers import create_numbered_prototype_image

import os

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
- 처리내용은 반드시 화면의 실제 UI 영역 하나와 사용자 요구사항 하나 이상을 연결해서 작성하라.
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

[선별된 사용자 요구사항]
{related_requirements}
"""


def normalize_text_for_match(value: Any) -> str:
    """요구사항 필터링에 사용할 텍스트를 소문자 문자열로 정리합니다."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(normalize_text_for_match(v) for v in value)
    if isinstance(value, dict):
        return " ".join(normalize_text_for_match(v) for v in value.values())
    return str(value).lower()


def extract_match_terms(text: str) -> List[str]:
    """화면 텍스트와 요구사항을 비교하기 위한 핵심 토큰을 추출합니다."""
    stopwords = {
        "string", "number", "null", "true", "false", "화면", "사용자", "시스템", "요구사항",
        "기능", "처리", "관리", "제공", "지원", "정보", "데이터", "서비스", "설계", "구현",
        "확인", "조회", "입력", "출력", "목록", "상태", "결과", "내용", "기반", "관련"
    }
    terms = re.findall(r"[가-힣A-Za-z0-9_]{2,}", text.lower())
    return [term for term in terms if term not in stopwords and len(term) >= 2]


def compact_requirement(requirement: Dict[str, Any], max_text_len: int = 420) -> Dict[str, Any]:
    """모델 입력 토큰을 줄이기 위해 요구사항의 핵심 필드만 압축합니다."""
    compact = {
        "requirement_id": requirement.get("requirement_id") or "",
        "requirement_name": requirement.get("requirement_name") or "",
        "requirement_type": requirement.get("requirement_type") or "",
        "description": requirement.get("description") or "",
        "constraints": requirement.get("constraints") or [],
        "validation_criteria": requirement.get("validation_criteria") or [],
    }
    for key in ["description"]:
        if len(str(compact[key])) > max_text_len:
            compact[key] = str(compact[key])[:max_text_len].rstrip() + "..."
    compact["constraints"] = [str(v)[:180] for v in compact["constraints"][:3]]
    compact["validation_criteria"] = [str(v)[:160] for v in compact["validation_criteria"][:3]]
    return compact


def build_screen_match_context(image_path: Path, ui_observation: Dict[str, Any]) -> str:
    """이미지 관찰 결과와 파일명을 합쳐 요구사항 매칭용 화면 문맥을 만듭니다."""
    parts = [image_path.stem]
    parts.extend(ui_observation.get("screen_name_candidates", []) or [])
    parts.extend(ui_observation.get("menu_path_candidates", []) or [])
    parts.extend(ui_observation.get("visible_texts", []) or [])
    for area in ui_observation.get("functional_areas", []) or []:
        parts.append(area.get("name", ""))
        parts.append(area.get("area_role", ""))
        parts.extend(area.get("visible_texts", []) or [])
    return normalize_text_for_match(parts)


def select_related_requirements(requirement_summary: Dict[str, Any], ui_observation: Dict[str, Any], image_path: Path, limit: int = 10) -> List[Dict[str, Any]]:
    """화면 관찰 결과와 겹치는 키워드가 많은 요구사항을 우선 선별합니다."""
    requirements = requirement_summary.get("requirements", []) or []
    screen_context = build_screen_match_context(image_path, ui_observation)
    screen_terms = set(extract_match_terms(screen_context))
    scored = []
    for order, req in enumerate(requirements):
        compact = compact_requirement(req)
        req_text = normalize_text_for_match(compact)
        req_terms = set(extract_match_terms(req_text))
        overlap = screen_terms & req_terms
        score = len(overlap) * 3
        for term in screen_terms:
            if term and term in req_text:
                score += 1
        if score > 0:
            item = dict(compact)
            item["match_score"] = score
            item["matched_terms"] = sorted(overlap)[:12]
            scored.append((score, -order, item))

    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
    selected = [item for _, _, item in scored[:limit]]
    if selected:
        return selected
    return [compact_requirement(req) for req in requirements[:limit]]


def normalize_ui_observation(data: Any) -> Dict[str, Any]:
    """이미지 1차 분석 결과가 흔들려도 후속 단계에서 쓸 수 있는 형태로 정리합니다."""
    if not isinstance(data, dict):
        data = {}
    data.setdefault("screen_name_candidates", [])
    data.setdefault("menu_path_candidates", [])
    data.setdefault("visible_texts", [])
    data.setdefault("functional_areas", [])
    if not isinstance(data["functional_areas"], list):
        data["functional_areas"] = []
    normalized_areas = []
    for area in data["functional_areas"]:
        if not isinstance(area, dict):
            continue
        normalized_areas.append({
            "name": str(area.get("name") or ""),
            "visible_texts": area.get("visible_texts") if isinstance(area.get("visible_texts"), list) else [],
            "area_role": str(area.get("area_role") or ""),
            "x_ratio": safe_ratio(area.get("x_ratio"), 0.5),
            "y_ratio": safe_ratio(area.get("y_ratio"), 0.5),
        })
    data["functional_areas"] = normalized_areas
    return data


def safe_ratio(value: Any, default: float) -> float:
    """번호 버튼 좌표를 0과 1 사이의 실수로 보정합니다."""
    try:
        ratio = float(value)
    except Exception:
        ratio = default
    return max(0.03, min(0.97, ratio))


def normalize_screen_spec(data: Any, image_path: Path, ui_observation: Dict[str, Any], idx: int) -> Dict[str, Any]:
    """모델이 생성한 화면 상세 설계 JSON을 DOCX 생성에 맞는 형태로 정리합니다."""
    if not isinstance(data, dict):
        raise ValueError("화면 상세 설계 결과가 JSON 객체가 아닙니다.")
    screen_candidates = [v for v in ui_observation.get("screen_name_candidates", []) if str(v).strip()]
    data["screen_id"] = f"UI-{idx:03d}"
    data["screen_name"] = str(data.get("screen_name") or (screen_candidates[0] if screen_candidates else image_path.stem)).strip()
    data["screen_type"] = str(data.get("screen_type") or ui_observation.get("screen_type") or "").strip()
    menu_candidates = [v for v in ui_observation.get("menu_path_candidates", []) if str(v).strip()]
    data["menu_path"] = str(data.get("menu_path") or (menu_candidates[0] if menu_candidates else data["screen_name"])).strip()
    data["screen_overview"] = str(data.get("screen_overview") or "").strip()

    process_contents = data.get("process_contents", [])
    if not isinstance(process_contents, list):
        process_contents = []
    normalized_process = []
    for pos, item in enumerate(process_contents, start=1):
        if not isinstance(item, dict):
            continue
        normalized_process.append({
            "no": pos,
            "title": str(item.get("title") or "").strip(),
            "description": str(item.get("description") or "").strip(),
            "requirement_basis": str(item.get("requirement_basis") or "").strip(),
        })
    data["process_contents"] = normalized_process

    markers = data.get("button_markers", [])
    if not isinstance(markers, list):
        markers = []
    marker_by_no = {}
    for marker in markers:
        if not isinstance(marker, dict):
            continue
        try:
            no = int(marker.get("no"))
        except Exception:
            continue
        marker_by_no[no] = {
            "no": no,
            "target_area": str(marker.get("target_area") or ""),
            "x_ratio": safe_ratio(marker.get("x_ratio"), 0.5),
            "y_ratio": safe_ratio(marker.get("y_ratio"), 0.5),
        }

    areas = ui_observation.get("functional_areas", []) or []
    normalized_markers = []
    for pos, process in enumerate(data["process_contents"], start=1):
        marker = marker_by_no.get(pos)
        if marker is None:
            area = areas[pos - 1] if pos - 1 < len(areas) else {}
            marker = {
                "no": pos,
                "target_area": area.get("name") or process.get("title") or "",
                "x_ratio": safe_ratio(area.get("x_ratio"), 0.5),
                "y_ratio": safe_ratio(area.get("y_ratio"), 0.12 + min(pos, 8) * 0.09),
            }
        marker["no"] = pos
        normalized_markers.append(marker)
    data["button_markers"] = normalized_markers
    return data


def validate_screen_spec_quality(spec: Dict[str, Any]) -> List[str]:
    """반복 출력과 부실한 처리내용을 감지합니다."""
    issues = []
    process_contents = spec.get("process_contents", []) or []
    if len(process_contents) < 3:
        issues.append("처리내용이 3개 미만입니다.")
    titles = [str(item.get("title", "")).strip() for item in process_contents]
    descriptions = [str(item.get("description", "")).strip() for item in process_contents]
    bases = [str(item.get("requirement_basis", "")).strip() for item in process_contents]
    screen_name = str(spec.get("screen_name", "")).strip()
    if titles and len(set(titles)) <= max(1, len(titles) // 3):
        issues.append("처리내용 제목 반복이 많습니다.")
    if descriptions and len(set(descriptions)) <= max(1, len(descriptions) // 3):
        issues.append("처리내용 설명 반복이 많습니다.")
    if bases and len(set(bases)) <= max(1, len(bases) // 3):
        issues.append("요구사항 근거 반복이 많습니다.")
    repeated_screen_name = sum(1 for value in titles + descriptions + bases if value == screen_name)
    if repeated_screen_name >= max(2, len(process_contents)):
        issues.append("화면명만 반복된 항목이 많습니다.")
    short_descriptions = [value for value in descriptions if len(value) < 18]
    if len(short_descriptions) >= max(2, len(descriptions) // 2):
        issues.append("처리내용 설명이 너무 짧습니다.")
    marker_nos = {int(m.get("no")) for m in spec.get("button_markers", []) or [] if isinstance(m, dict) and str(m.get("no", "")).isdigit()}
    process_nos = {int(p.get("no")) for p in process_contents if isinstance(p, dict) and str(p.get("no", "")).isdigit()}
    if process_nos != marker_nos:
        issues.append("처리내용 번호와 버튼 번호가 일치하지 않습니다.")
    return issues


def format_requirement_basis(requirement: Dict[str, Any]) -> str:
    """처리내용에 붙일 요구사항 근거 문자열을 구성합니다."""
    req_id = str(requirement.get("requirement_id") or "").strip()
    req_name = str(requirement.get("requirement_name") or "").strip()
    if req_id and req_name:
        return f"{req_id} {req_name}"
    return req_id or req_name or "관련 요구사항"


def build_process_from_observation(
    ui_observation: Dict[str, Any],
    related_requirements: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """모델 상세 JSON이 빈약할 때 UI 관찰 결과로 처리내용을 보강합니다."""
    areas = ui_observation.get("functional_areas", []) or []
    visible_texts = [str(v).strip() for v in ui_observation.get("visible_texts", []) or [] if str(v).strip()]
    items = []

    if areas:
        for idx, area in enumerate(areas[:8], start=1):
            title = str(area.get("name") or "").strip() or f"기능 영역 {idx}"
            role = str(area.get("area_role") or "").strip()
            texts = [str(v).strip() for v in area.get("visible_texts", []) or [] if str(v).strip()]
            basis = format_requirement_basis(related_requirements[(idx - 1) % len(related_requirements)]) if related_requirements else "관련 요구사항"
            detail = role or "화면에 표시된 기능 영역을 기준으로 사용자가 조회, 선택 또는 실행할 수 있도록 구성한다."
            if texts:
                detail += " 표시 텍스트: " + ", ".join(texts[:5])
            items.append({
                "no": idx,
                "title": title,
                "description": detail,
                "requirement_basis": basis,
            })

    if not items:
        fallback_names = visible_texts[:5] or ["화면 정보 확인", "주요 기능 실행", "처리 결과 확인"]
        for idx, title in enumerate(fallback_names[:8], start=1):
            basis = format_requirement_basis(related_requirements[(idx - 1) % len(related_requirements)]) if related_requirements else "관련 요구사항"
            items.append({
                "no": idx,
                "title": title,
                "description": "프로토타입 화면에 표시된 내용을 기준으로 사용자가 해당 정보를 확인하고 필요한 업무 처리를 수행한다.",
                "requirement_basis": basis,
            })

    return items


def build_markers_from_observation(
    process_contents: List[Dict[str, Any]],
    ui_observation: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """UI 관찰 좌표를 이용해 처리내용 번호와 1:1로 맞는 버튼 마커를 구성합니다."""
    areas = ui_observation.get("functional_areas", []) or []
    markers = []
    for idx, process in enumerate(process_contents, start=1):
        area = areas[idx - 1] if idx - 1 < len(areas) else {}
        markers.append({
            "no": idx,
            "target_area": area.get("name") or process.get("title") or f"기능 영역 {idx}",
            "x_ratio": safe_ratio(area.get("x_ratio"), 0.12 + ((idx - 1) % 3) * 0.36),
            "y_ratio": safe_ratio(area.get("y_ratio"), 0.18 + min(idx - 1, 6) * 0.11),
        })
    return markers


def ensure_screen_spec_content(
    data: Dict[str, Any],
    image_path: Path,
    ui_observation: Dict[str, Any],
    related_requirements: List[Dict[str, Any]],
    idx: int,
) -> Dict[str, Any]:
    """화면 상세/처리내용/버튼 마커가 비어 있으면 관찰 결과 기반으로 보강합니다."""
    data = normalize_screen_spec(data, image_path, ui_observation, idx)
    if not data.get("screen_overview"):
        visible_texts = [str(v).strip() for v in ui_observation.get("visible_texts", []) or [] if str(v).strip()]
        data["screen_overview"] = (
            "프로토타입 화면의 주요 텍스트와 기능 영역을 기준으로 사용자 인터페이스 구성을 정의한다."
            if not visible_texts
            else "프로토타입 화면에 표시된 주요 정보와 기능 영역을 기준으로 사용자 인터페이스 구성을 정의한다."
        )
    if len(data.get("process_contents", []) or []) < 2:
        data["process_contents"] = build_process_from_observation(ui_observation, related_requirements)
    if len(data.get("button_markers", []) or []) != len(data.get("process_contents", []) or []):
        data["button_markers"] = build_markers_from_observation(data.get("process_contents", []), ui_observation)
    return normalize_screen_spec(data, image_path, ui_observation, idx)


def build_fallback_ui_observation(image_path: Path) -> Dict[str, Any]:
    """VLM을 사용할 수 없을 때 파일명 기반으로 최소 화면 관찰 결과를 만든다."""
    name = re.sub(r"^\d+_", "", image_path.stem)
    name = re.sub(r"^ui_prototype_\d+_\d+_", "", name, flags=re.IGNORECASE)
    screen_name = name.replace("_", " ").strip() or f"화면 {image_path.stem}"
    visible_texts = [screen_name, "조회", "검색", "상세", "저장"]
    return normalize_ui_observation({
        "screen_name_candidates": [screen_name],
        "screen_type": "업무 화면",
        "menu_path_candidates": [screen_name],
        "visible_texts": visible_texts,
        "functional_areas": [
            {
                "name": "화면 제목 및 메뉴 영역",
                "visible_texts": [screen_name],
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
    })


def build_fallback_screen_spec(image_path: Path, requirement_summary: Dict[str, Any], idx: int) -> Dict[str, Any]:
    """VLM 실패 시에도 DOCX 생성을 계속하기 위한 최소 화면 상세 설계."""
    ui_observation = build_fallback_ui_observation(image_path)
    related_requirements = select_related_requirements(requirement_summary, ui_observation, image_path, limit=10)
    data = ensure_screen_spec_content({}, image_path, ui_observation, related_requirements, idx)
    data["ui_observation"] = ui_observation
    data["related_requirements"] = related_requirements
    data["quality_issues"] = ["VLM 분석 실패로 파일명/요구사항 기반 fallback 생성"]
    data["image_path"] = str(image_path)
    data["annotated_image_path"] = str(create_numbered_prototype_image(image_path, data, WORK_DIR / "numbered_images"))
    return data


def analyze_screen_image(image_path: Path, requirement_summary: Dict[str, Any], idx: int) -> Dict[str, Any]:
    """이미지 관찰, 요구사항 선별, 상세 설계 생성을 순서대로 수행합니다."""
    use_vlm = os.getenv("INTERFACE_VLM_ENABLED", "false").strip().lower() in {"1", "true", "yes", "y"}
    if not use_vlm:
        print(f"VLM 분석 생략: {image_path.name} (INTERFACE_VLM_ENABLED=false)")
        return build_fallback_screen_spec(image_path, requirement_summary, idx)

    try:
        raw_observation = qwen_analyze_image(image_path, UI_ELEMENT_ANALYSIS_PROMPT, max_new_tokens=MAX_NEW_TOKENS_SCREEN)
    except Exception as e:
        print(f"VLM 분석 실패, fallback 사용: {image_path.name}")
        print(type(e).__name__, str(e)[:500])
        return build_fallback_screen_spec(image_path, requirement_summary, idx)

    raw_dir = WORK_DIR / "model_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{idx:03d}_{image_path.stem}_observation.txt").write_text(raw_observation, encoding="utf-8")
    try:
        ui_observation = normalize_ui_observation(parse_or_repair_json(raw_observation, "UI 관찰 JSON", max_new_tokens=MAX_NEW_TOKENS_SCREEN))
    except Exception as e:
        print(f"UI 관찰 JSON 파싱 실패: {image_path.name}")
        print(raw_observation[:1000])
        raise RuntimeError("UI 관찰 JSON 생성에 실패했습니다. 하드코딩 fallback은 사용하지 않습니다.") from e

    related_requirements = select_related_requirements(requirement_summary, ui_observation, image_path, limit=10)
    detail_prompt = (
        SCREEN_DETAIL_PROMPT
        .replace("{image_name}", image_path.name)
        .replace("{ui_observation}", json.dumps(ui_observation, ensure_ascii=False, indent=2)[:5000])
        .replace("{related_requirements}", json.dumps(related_requirements, ensure_ascii=False, indent=2)[:7000])
    )
    raw_detail = qwen_analyze_image(image_path, detail_prompt, max_new_tokens=MAX_NEW_TOKENS_SCREEN)
    (raw_dir / f"{idx:03d}_{image_path.stem}_detail.txt").write_text(raw_detail, encoding="utf-8")
    try:
        data = ensure_screen_spec_content(
            parse_or_repair_json(raw_detail, "화면 상세 설계 JSON", max_new_tokens=MAX_NEW_TOKENS_SCREEN),
            image_path,
            ui_observation,
            related_requirements,
            idx,
        )
    except Exception as e:
        print(f"이미지 분석 JSON 파싱 실패: {image_path.name}")
        print(raw_detail[:1000])
        data = ensure_screen_spec_content({}, image_path, ui_observation, related_requirements, idx)

    quality_issues = validate_screen_spec_quality(data)
    if quality_issues:
        retry_prompt = detail_prompt + "\n\n[품질 검증 실패 항목]\n" + json.dumps(quality_issues, ensure_ascii=False) + "\n위 문제를 반드시 수정해서 JSON만 다시 출력하라."
        raw_retry = qwen_analyze_image(image_path, retry_prompt, max_new_tokens=MAX_NEW_TOKENS_SCREEN)
        try:
            raw_dir.mkdir(parents=True, exist_ok=True)
            (raw_dir / f"{idx:03d}_{image_path.stem}_retry.txt").write_text(raw_retry, encoding="utf-8")
            retry_data = ensure_screen_spec_content(
                parse_or_repair_json(raw_retry, "화면 상세 설계 재생성 JSON", max_new_tokens=MAX_NEW_TOKENS_SCREEN),
                image_path,
                ui_observation,
                related_requirements,
                idx,
            )
            retry_issues = validate_screen_spec_quality(retry_data)
            if len(retry_issues) <= len(quality_issues):
                data = retry_data
                quality_issues = retry_issues
        except Exception as e:
            print("품질 재생성 결과를 사용하지 못했습니다:", type(e).__name__, str(e)[:300])

    data["ui_observation"] = ui_observation
    data["related_requirements"] = related_requirements
    data["quality_issues"] = quality_issues
    data["image_path"] = str(image_path)
    data["annotated_image_path"] = str(create_numbered_prototype_image(image_path, data, WORK_DIR / "numbered_images"))
    if quality_issues:
        print(f"품질 경고({image_path.name}):", quality_issues)
    return data

STRUCTURE_PROMPT = """
너는 사용자 인터페이스 설계서의 "1. 사용자 인터페이스 구조도"를 작성하는 설계자다.

아래 화면 목록을 보고 Level 1~Level 4 구조로 메뉴/화면 계층을 정리하라.

반드시 JSON 배열로만 출력하라. 마크다운 금지.

출력 JSON schema:
[
  {
    "level1": "string",
    "level2": "string",
    "level3": "string",
    "level4": "string"
  }
]

규칙:
- Level 1은 가능한 한 전체 시스템 또는 업무 영역이다.
- Level 2는 주요 메뉴 또는 서브시스템이다.
- Level 3은 화면 그룹 또는 처리 유형이다.
- Level 4는 실제 화면명 또는 세부 기능이다.
- 화면 상세 설계의 화면명이 Level 4에 최소 1회 이상 등장하게 하라.

[화면 목록]
{screen_list}
"""


def normalize_ui_structure_data(data: Any, screen_specs: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """구조도 모델 출력이 단일 객체/배열/문자열이어도 DOCX 표에 넣을 수 있는 목록으로 정리합니다."""
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        data = []

    rows = []
    for item in data:
        if isinstance(item, dict):
            rows.append({
                "level1": str(item.get("level1", "")),
                "level2": str(item.get("level2", "")),
                "level3": str(item.get("level3", "")),
                "level4": str(item.get("level4", "")),
            })

    if rows:
        return rows

    fallback_rows = []
    for s in screen_specs:
        menu_parts = [part.strip() for part in str(s.get("menu_path") or "").split("/") if part.strip()]
        fallback_rows.append({
            "level1": menu_parts[0] if len(menu_parts) > 0 else (s.get("screen_type") or ""),
            "level2": menu_parts[1] if len(menu_parts) > 1 else "",
            "level3": menu_parts[2] if len(menu_parts) > 2 else (s.get("screen_type") or ""),
            "level4": s.get("screen_name") or s.get("screen_id") or "",
        })
    return fallback_rows


def generate_ui_structure(screen_specs: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """분석된 화면 목록을 기반으로 UI 메뉴 구조도를 생성합니다."""
    use_vlm = os.getenv("INTERFACE_VLM_ENABLED", "false").strip().lower() in {"1", "true", "yes", "y"}
    if not use_vlm:
        return normalize_ui_structure_data([], screen_specs)

    screen_list = [
        {
            "screen_id": s.get("screen_id"),
            "screen_name": s.get("screen_name"),
            "menu_path": s.get("menu_path"),
            "screen_type": s.get("screen_type")
        }
        for s in screen_specs
    ]
    prompt = STRUCTURE_PROMPT.replace(
        "{screen_list}", json.dumps(screen_list, ensure_ascii=False, indent=2)
    )
    try:
        raw = qwen_generate_text(prompt, max_new_tokens=MAX_NEW_TOKENS_FINAL)
        return normalize_ui_structure_data(parse_or_repair_json(raw, "사용자 인터페이스 구조도 JSON", max_new_tokens=MAX_NEW_TOKENS_FINAL), screen_specs)
    except Exception as e:
        print("구조도 생성 실패. 화면 목록 기반 기본 구조도를 사용합니다.")
        print(type(e).__name__, str(e)[:500])
        return normalize_ui_structure_data([], screen_specs)
