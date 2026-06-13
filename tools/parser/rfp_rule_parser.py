"""RFP DOCX 표에서 요구사항 항목을 추출하는 Rule Parser입니다."""

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from docx import Document

from tools.result import ToolResult, error_result, success_result


RuleParser = Callable[[str], Any]

ID_PATTERN = re.compile(r"^[A-Za-z]{2,5}[\-\u2013\u2014]\d{2,4}$")

DEFAULT_PREFIX_MAP = {
    "SFR": "기능",
    "FUR": "기능",
    "NFR": "비기능",
    "PER": "성능",
    "SER": "보안",
    "SEC": "보안",
    "QUR": "품질",
    "TER": "테스트",
    "TST": "테스트",
    "DAR": "데이터",
    "DBR": "데이터",
    "CSR": "컨설팅",
    "PSR": "프로젝트 지원",
    "PMR": "프로젝트 관리",
    "COR": "제약사항",
    "INT": "인터페이스",
    "INR": "인터페이스",
    "SIR": "시스템 장비구성",
    "MPR": "유지보수",
}

FIELD_ALIASES = {
    "name": {
        "요구사항명",
        "요구사항 명",
        "요구사항 명칭",
        "기능명",
        "기능 명",
        "항목명",
        "업무명",
    },
    "type": {"요구사항분류", "요구사항 구분", "구분", "분류", "유형"},
    "description": {"요구사항 상세설명", "상세설명", "상세 설명", "세부내용", "세부 내용", "정의"},
    "constraint": {"제약사항", "특이사항", "조건", "비고"},
    "validation": {"검증기준", "시험기준", "평가기준", "검수기준", "검토기준"},
    "priority": {"우선순위", "중요도"},
    "source_ref": {"관련 요구사항", "관련요구사항", "출처", "근거"},
}

BLACKLIST = {
    "요구사항명",
    "요구사항 명",
    "요구사항 명칭",
    "요구사항 고유번호",
    "요구사항 상세설명",
    "상세설명",
    "상세 설명",
    "세부내용",
    "세부 내용",
    "정의",
    "산출정보",
    "관련 요구사항",
    "관련요구사항",
    "검토기준",
    "검증기준",
    "비고",
    "구분",
    "분류",
    "유형",
    "사업수행계획서",
    "설계서",
    "결과보고서",
}


def parse_rfp_requirements(
    file_path: str,
    *,
    parser: RuleParser | None = None,
) -> ToolResult:
    """RFP 파일에서 요구사항 목록을 추출해 공통 ToolResult로 반환합니다."""

    selected_parser = parser or extract_requirements_from_rfp_docx
    try:
        requirements = selected_parser(file_path)
        return success_result({"file_path": file_path, "requirements": requirements})
    except Exception as exc:
        return error_result("RFP_RULE_PARSE_FAILED", str(exc), {"file_path": file_path})


def extract_requirements_from_rfp_docx(file_path: str) -> list[dict[str, Any]]:
    """DOCX 표를 순회하며 요구사항 ID 기준으로 항목을 구성합니다."""

    path = Path(file_path)
    document = Document(str(path))
    requirements_map: dict[str, dict[str, Any]] = {}

    for table_index, table in enumerate(document.tables):
        last_id: str | None = None
        for row_index, row in enumerate(table.rows):
            cells = _unique_cells(row.cells)
            if not cells:
                continue

            requirement_id = _find_requirement_id(cells)
            if requirement_id:
                last_id = requirement_id
                current = requirements_map.setdefault(
                    requirement_id,
                    _new_requirement(requirement_id, path.name, table_index, row_index),
                )
                current["desc_parts"].extend(
                    cell for cell in cells if _normalize_id(cell) != requirement_id
                )
                continue

            if not last_id:
                continue

            current = requirements_map[last_id]
            if len(cells) >= 2:
                field = _detect_field(cells[0])
                value = " ".join(cells[1:]).strip()
                if field == "name":
                    current["name"] = value
                    continue
                if field == "type":
                    current["type"] = value
                    continue
                if field == "description":
                    current["desc_parts"].append(value)
                    continue
                if field == "constraint":
                    current["constraints"].append(value)
                    continue
                if field == "validation":
                    current["validation_criteria"].append(value)
                    continue
                if field == "priority":
                    current["priority"] = value
                    continue
                if field == "source_ref":
                    current["source_refs"].append(value)
                    continue
                if "산출정보" in cells[0]:
                    continue

            current["desc_parts"].extend(cell for cell in cells if cell not in BLACKLIST)

    return [_build_requirement(data) for data in requirements_map.values() if _is_valid_requirement(data)]


def _new_requirement(
    requirement_id: str,
    file_name: str,
    table_index: int,
    row_index: int,
) -> dict[str, Any]:
    return {
        "id": requirement_id,
        "name": None,
        "type": None,
        "priority": None,
        "constraints": [],
        "validation_criteria": [],
        "source_refs": [],
        "desc_parts": [],
        "source": file_name,
        "table_index": table_index,
        "row_index": row_index,
    }


def _build_requirement(data: dict[str, Any]) -> dict[str, Any]:
    req_id = data["id"]
    unique_parts = _clean_parts(data["desc_parts"])
    name = data["name"] or _infer_requirement_name(unique_parts)
    description = _clean_description("\n".join(unique_parts))
    req_type = data["type"] or _infer_requirement_type(req_id, name, description)
    source_refs = list(dict.fromkeys([*data["source_refs"], req_id]))
    validation_criteria = list(dict.fromkeys(data["validation_criteria"])) or ["검토 필요"]
    constraints = list(dict.fromkeys(data["constraints"]))

    return {
        "requirement_id": req_id,
        "requirement_name": name[:100],
        "requirement_type": req_type,
        "description": description,
        "source": [data["source"]],
        "constraints": constraints,
        "priority": data["priority"] or "미지정",
        "validation_criteria": validation_criteria,
        "note": None,
        "source_refs": source_refs,
        "metadata": {
            "source_file": data["source"],
            "table_index": data["table_index"],
            "row_index": data["row_index"],
        },
        "req_id": req_id,
        "req_name": name[:100],
        "detail_text": description,
        "source_req_ids": source_refs,
    }


def _unique_cells(cells: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for cell in cells:
        text = normalize_text(cell.text)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _find_requirement_id(cells: list[str]) -> str | None:
    for cell in cells:
        normalized = _normalize_id(cell)
        if ID_PATTERN.match(normalized):
            return normalized
    return None


def _normalize_id(text: str) -> str:
    return re.sub(r"[\-\u2013\u2014]", "-", text.strip()).upper()


def normalize_text(text: str) -> str:
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _detect_field(text: str) -> str | None:
    normalized = normalize_text(text)
    for field, aliases in FIELD_ALIASES.items():
        if any(normalized == alias or alias in normalized for alias in aliases):
            return field
    return None


def _clean_parts(parts: list[str]) -> list[str]:
    unique_parts: list[str] = []
    seen: set[str] = set()
    for part in parts:
        text = normalize_text(part)
        if not text or text in BLACKLIST or len(text) <= 2 or text in seen:
            continue
        seen.add(text)
        unique_parts.append(text)
    return unique_parts


def _clean_description(description: str) -> str:
    description = re.sub(
        r"(요구사항\s*고유번호|요구사항\s*상세설명|세부내용|정의)",
        "",
        description,
    )
    description = re.sub(r"\n{2,}", "\n", description)
    return description.strip()


def _is_valid_requirement(data: dict[str, Any]) -> bool:
    req_id = data["id"]
    if req_id.endswith("-000") or req_id.endswith("-00"):
        return False
    return len(_clean_description("\n".join(_clean_parts(data["desc_parts"])))) > 20


def _infer_requirement_name(parts: list[str]) -> str:
    for part in parts:
        text = normalize_text(part)
        if len(text) < 4 or text.isdigit() or text in BLACKLIST:
            continue
        if "요구사항" in text and len(text) < 20:
            continue
        return text[:100]
    return "미분류"


def _infer_requirement_type(req_id: str, name: str, description: str) -> str:
    name_text = normalize_text(name)
    if "보안" in name_text:
        return "보안"
    if "성능" in name_text:
        return "성능"
    if "품질" in name_text:
        return "품질"
    if "인터페이스" in name_text or "UI" in name_text.upper():
        return "인터페이스"
    if "데이터" in name_text:
        return "데이터"
    if "프로젝트 지원" in name_text:
        return "프로젝트 지원"
    if "지원" in name_text:
        return "프로젝트 지원"
    if "장비구성" in name_text or "인프라" in name_text:
        return "시스템 장비구성"

    prefix = req_id.split("-")[0].upper()
    if prefix in DEFAULT_PREFIX_MAP:
        return DEFAULT_PREFIX_MAP[prefix]

    text = f"{name} {description[:500]}".lower()
    if any(keyword in text for keyword in ("보안", "암호화", "접근제어", "접근 통제", "개인정보")):
        return "보안"
    if any(keyword in text for keyword in ("처리량", "응답속도", "동시접속", "throughput")):
        return "성능"
    if any(keyword in text for keyword in ("인프라", "서버", "아키텍처")):
        return "시스템 장비구성"
    return "기능"


def dump_requirements_json(requirements: list[dict[str, Any]]) -> str:
    """수동 검증과 CLI 출력에 쓰는 JSON 직렬화 helper입니다."""

    return json.dumps({"requirements": requirements}, ensure_ascii=False, indent=2)
