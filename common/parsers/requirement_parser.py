import json
import re
from typing import Any


REQ_ID_PATTERN = re.compile(
    r"\b((?:REQ|SFR|SIR|COR|CMR|FQR|SEC|PER|AST|GCL|ISR|DAR|WTR|UOR|PRM|OPS|MNG|CSR|ECR|TER|SER|INR|QUR|PMR|PSR)-?\d{3,5})\b",
    re.IGNORECASE,
)


def parse_requirement_to_json(requirement_text: str) -> dict[str, list[dict[str, Any]]]:
    parsed_json = _try_parse_json(requirement_text)
    if parsed_json:
        return _normalize_requirement_document(parsed_json)

    matches = list(REQ_ID_PATTERN.finditer(requirement_text or ""))
    if matches:
        requirements = []
        for idx, match in enumerate(matches, start=1):
            start = match.start()
            end = matches[idx].start() if idx < len(matches) else len(requirement_text)
            block = requirement_text[start:end].strip()
            requirements.append(_parse_requirement_block(block, match.group(1).upper(), idx))
        return {"requirements": requirements}

    text = (requirement_text or "").strip()
    if not text:
        return {"requirements": []}

    return {
        "requirements": [
            {
                "requirement_id": "REQ-001",
                "requirement_name": _guess_name(text) or "요구사항",
                "description": text[:3000],
                "validation_criteria": _pick_lines(text, ["검증", "확인", "테스트", "성공", "완료"]),
                "related_screen": [],
                "related_api": [],
                "keywords": _extract_keywords(text),
            }
        ]
    }


def _try_parse_json(text: str) -> Any:
    value = (text or "").strip()
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        pass
    match = re.search(r"(\{.*\}|\[.*\])", value, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _normalize_requirement_document(data: Any) -> dict[str, list[dict[str, Any]]]:
    if isinstance(data, dict):
        items = data.get("requirements") or data.get("final_reqs") or []
    elif isinstance(data, list):
        items = data
    else:
        items = []

    requirements = []
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        description = str(item.get("description") or item.get("definition") or item.get("content") or "")
        validation = item.get("validation_criteria") or item.get("test_criteria") or []
        requirements.append(
            {
                "requirement_id": str(item.get("requirement_id") or item.get("req_id") or f"REQ-{idx:03d}"),
                "requirement_name": str(item.get("requirement_name") or item.get("name") or _guess_name(description) or f"요구사항_{idx:03d}"),
                "description": description,
                "validation_criteria": _as_list(validation),
                "related_screen": _as_list(item.get("related_screen")),
                "related_api": _as_list(item.get("related_api")),
                "keywords": _as_list(item.get("keywords")) or _extract_keywords(description),
            }
        )
    return {"requirements": requirements}


def _parse_requirement_block(block: str, req_id: str, idx: int) -> dict[str, Any]:
    lines = [line.strip(" -|•\t") for line in block.splitlines() if line.strip()]
    title = _guess_name("\n".join(lines[:3])).replace(req_id, "").strip(" :-|") or f"요구사항_{idx:03d}"
    return {
        "requirement_id": req_id,
        "requirement_name": title,
        "description": block[:3000],
        "validation_criteria": _pick_lines(block, ["검증", "확인", "테스트", "성공", "완료"]),
        "related_screen": [],
        "related_api": [],
        "keywords": _extract_keywords(block),
    }


def _guess_name(text: str) -> str:
    for line in (text or "").splitlines():
        value = line.strip(" -|•\t")
        if value:
            return value[:80]
    return ""


def _pick_lines(text: str, keywords: list[str], limit: int = 6) -> list[str]:
    lines = [line.strip(" -|•\t") for line in (text or "").splitlines() if line.strip()]
    picked = [line for line in lines if any(keyword in line for keyword in keywords)]
    return list(dict.fromkeys(picked))[:limit]


def _extract_keywords(text: str, limit: int = 12) -> list[str]:
    stopwords = {"요구사항", "시스템", "기능", "제공", "한다", "하여야", "사용", "관리", "지원", "대한"}
    result = []
    for token in re.findall(r"[가-힣A-Za-z0-9]{2,}", text or ""):
        if token in stopwords or token.lower() in stopwords:
            continue
        if token not in result:
            result.append(token)
        if len(result) >= limit:
            break
    return result


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []
