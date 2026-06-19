from __future__ import annotations

import re
from typing import Any

from tools.llm.llm_client import LLMClient
from tools.llm.response_parser import parse_json_response
from tools.llm.send_api import send_parallel


def extract_constraints(search_results: list[dict[str, Any]]) -> list[str]:
    constraints: list[str] = []
    seen: set[str] = set()
    for text in _evidence_texts(search_results):
        constraint = _constraint_sentence(text)
        if constraint and constraint not in seen:
            constraints.append(constraint)
            seen.add(constraint)
        if len(constraints) >= 3:
            break
    return constraints


def extract_validation_criteria(search_results: list[dict[str, Any]]) -> list[str]:
    criteria: list[str] = []
    seen: set[str] = set()
    for text in _evidence_texts(search_results):
        criterion = _clean_validation_text(text)
        if criterion and criterion not in seen:
            criteria.append(criterion)
            seen.add(criterion)
        if len(criteria) >= 3:
            break
    return criteria


def constraints_to_validation_criteria(constraints: list[str]) -> list[str]:
    criteria: list[str] = []
    seen: set[str] = set()
    for constraint in constraints:
        criterion = _validation_sentence(constraint)
        if criterion and criterion not in seen:
            criteria.append(criterion)
            seen.add(criterion)
    return criteria


def normalize_task3_requirement(item: dict[str, Any]) -> dict[str, Any]:
    """Convert Task3 GOLD output to the fixed SRS CBD contract."""

    requirement_id = str(
        item.get("requirement_id")
        or item.get("gold_id")
        or item.get("req_id")
        or ""
    )
    requirement_name = str(item.get("requirement_name") or item.get("req_name") or "")
    description = str(
        item.get("description")
        or item.get("requirement_detail")
        or item.get("detail_text")
        or ""
    )
    source = _as_list(item.get("source") or item.get("sources") or item.get("source_req_ids"))
    return {
        "requirement_id": requirement_id,
        "requirement_name": requirement_name,
        "requirement_type": str(item.get("requirement_type") or "기능"),
        "description": description,
        "source": source,
        "constraints": _as_list(item.get("constraints")),
        "priority": [],
        "solution": [],
        "validation_criteria": _as_list(item.get("validation_criteria")),
        "note": item.get("note") or item.get("merge_basis") or "",
    }


def normalize_task3_output(value: Any) -> Any:
    """Normalize a Task3 document object/list to the fixed SRS requirement list."""

    items = value.get("final_requirements") if isinstance(value, dict) else value
    if not isinstance(items, list):
        return value
    if not any(
        isinstance(item, dict)
        and (item.get("gold_id") or item.get("merge_basis") or item.get("source_task2_ids"))
        for item in items
    ):
        return items
    return [normalize_task3_requirement(item) for item in items if isinstance(item, dict)]


def enrich_gold_requirements_parallel(
    gold_items: list[dict[str, Any]],
    rag_results_by_item: list[Any],
    *,
    llm_client: LLMClient | None = None,
    max_workers: int = 4,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Normalize GOLD rows and fill only supplemental SRS columns from RAG."""

    warnings: list[dict[str, Any]] = []
    fallback_items = [
        _merge_supplement(normalize_task3_requirement(item), _supplement_from_rag(results))
        for item, results in zip(gold_items, rag_results_by_item, strict=False)
    ]
    if llm_client is None or not gold_items:
        return fallback_items, warnings

    requests = [
        {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "GOLD 요구사항은 그대로 유지하고 RAG 근거에서 supplemental SRS columns만 작성하세요. "
                        "CBD 기준에서 제약사항은 요구사항이 수행되기 위하여 필요로 하는 법적 또는 기술적인 조건입니다. "
                        "검수기준은 요구사항을 구현한 후 구현에 대한 품질을 정량적 또는 정성적으로 측정할 수 있는 기준입니다. "
                        "rag_results.constraints 근거는 constraints 작성에 우선 사용하고, "
                        "rag_results.validation_criteria 근거는 validation_criteria 작성에 우선 사용하세요. "
                        "검수기준은 제약사항에서만 파생하지 말고 검수/인수/품질측정 근거가 있으면 그 내용을 직접 반영하세요. "
                        "note에는 제약사항과 검수기준을 그렇게 작성한 이유를 한 문장으로 간단히 작성하세요. "
                        "단, 기존 note 또는 merge_basis를 대체하지 말고 추가 설명만 작성하세요. "
                        "RAG 원문을 그대로 복사하지 말고 기능 요구사항에 직접 적용되는 문장으로 정제하세요. "
                        "계약, 하도급, 대금, 제안서 작성, 사업관리 일반사항은 제외하세요. "
                        "requirement_id, requirement_name, requirement_type, description, source, note는 수정하지 마세요. "
                        "반환 JSON 키는 constraints, validation_criteria, note, rag_validation만 허용합니다."
                    ),
                },
                {
                    "role": "user",
                    "content": str(
                        {
                            "requirement": normalize_task3_requirement(item),
                            "rag_results": _rag_evidence_bundle(rag_results),
                            "fallback_supplement": _supplement_from_rag(rag_results),
                        }
                    ),
                },
            ]
        }
        for item, rag_results in zip(gold_items, rag_results_by_item, strict=False)
    ]
    result = send_parallel(requests, client=llm_client, max_workers=max_workers)
    if not result["success"]:
        warnings.append({"code": "REQUIREMENT_RAG_SUPPLEMENT_LLM_FAILED", "message": result["error"]["message"]})
        return fallback_items, warnings

    enriched: list[dict[str, Any]] = []
    for index, item_result in enumerate(result["data"]):
        supplement = _supplement_from_rag(rag_results_by_item[index])
        if item_result and item_result["success"]:
            parsed = parse_json_response(item_result["data"])
            if parsed["success"] and isinstance(parsed["data"], dict):
                supplement = _normalize_supplement(parsed["data"], supplement)
        enriched.append(_merge_supplement(normalize_task3_requirement(gold_items[index]), supplement))
    return enriched, warnings


def _supplement_from_rag(search_results: Any) -> dict[str, Any]:
    constraint_results = _constraint_results(search_results)
    validation_results = _validation_results(search_results)
    all_results = _merge_result_lists(constraint_results, validation_results)
    constraints = extract_constraints(constraint_results)
    validation_criteria = extract_validation_criteria(validation_results)
    if not validation_criteria:
        validation_criteria = constraints_to_validation_criteria(constraints)
    evidence_applied = bool(constraints or validation_criteria)
    return {
        "constraints": constraints,
        "source": _evidence_source_ids(all_results) if evidence_applied else [],
        "priority": [],
        "solution": [],
        "validation_criteria": validation_criteria,
        "note": _build_rag_note(constraints, validation_criteria, constraint_results, validation_results),
        "rag_validation": {
            "status": "APPLIED" if evidence_applied else "NO_EVIDENCE",
            "evidence": _rag_evidence_bundle(search_results),
            "notes": "RAG evidence applied to supplemental SRS columns." if evidence_applied else "No RAG evidence found.",
        },
    }


def _normalize_supplement(raw: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    constraints = _normalize_constraints(raw.get("constraints", fallback.get("constraints", [])))
    validation_criteria = _normalize_validation_criteria(
        raw.get("validation_criteria", fallback.get("validation_criteria", [])),
        constraints,
    )
    source = _merge_unique(
        _as_list(fallback.get("source")),
        _as_list(raw.get("source")),
    ) if (constraints or validation_criteria) else []
    note = _clean_note_text(raw.get("note") or raw.get("rag_note") or fallback.get("note"))
    rag_validation = raw.get("rag_validation", fallback.get("rag_validation", {}))
    if not isinstance(rag_validation, dict):
        rag_validation = fallback.get("rag_validation", {})
    return {
        "constraints": constraints,
        "source": source,
        "priority": [],
        "solution": [],
        "validation_criteria": validation_criteria,
        "note": note,
        "rag_validation": rag_validation,
    }


def _merge_supplement(item: dict[str, Any], supplement: dict[str, Any]) -> dict[str, Any]:
    merged = dict(item)
    for key in ("constraints", "validation_criteria"):
        if not merged.get(key):
            merged[key] = supplement.get(key, [])
    if supplement.get("constraints") or supplement.get("validation_criteria"):
        merged["source"] = _merge_unique(
            _as_list(merged.get("source")),
            _as_list(supplement.get("source")),
        )
        merged["note"] = _append_note(str(merged.get("note") or ""), str(supplement.get("note") or ""))
    merged["priority"] = []
    merged["solution"] = []
    return merged


def _constraint_results(search_results: Any) -> list[dict[str, Any]]:
    if isinstance(search_results, dict):
        value = search_results.get("constraints")
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
    if isinstance(search_results, list):
        return [item for item in search_results if isinstance(item, dict)]
    return []


def _validation_results(search_results: Any) -> list[dict[str, Any]]:
    if isinstance(search_results, dict):
        value = search_results.get("validation_criteria")
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
    if isinstance(search_results, list):
        return [item for item in search_results if isinstance(item, dict)]
    return []


def _rag_evidence_bundle(search_results: Any) -> dict[str, list[dict[str, Any]]]:
    return {
        "constraints": _constraint_results(search_results),
        "validation_criteria": _validation_results(search_results),
    }


def _merge_result_lists(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            key = str(item.get("citation") or item.get("content") or item.get("title") or id(item))
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def _evidence_texts(search_results: list[dict[str, Any]]) -> list[str]:
    texts: list[str] = []
    for result in search_results:
        metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
        title = str(result.get("title") or metadata.get("requirement_name") or "").strip()
        content = str(
            result.get("content")
            or metadata.get("content")
            or metadata.get("original_text")
            or metadata.get("text")
            or ""
        ).strip()
        candidate = " - ".join(part for part in (title, content) if part)
        if candidate and not _is_blocked_evidence(candidate):
            texts.append(candidate)
    return texts


def _evidence_source_ids(search_results: list[dict[str, Any]]) -> list[str]:
    source_ids: list[str] = []
    for result in search_results:
        metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
        for key in (
            "requirement_id",
            "req_id",
            "source_requirement_id",
            "source_req_id",
            "requirement_source_id",
        ):
            source_ids.extend(_as_list(metadata.get(key)))
        source_ids.extend(_as_list(result.get("requirement_id")))
    return _merge_unique([], source_ids)


def _constraint_sentence(text: str) -> str:
    cleaned = _clean_evidence_text(text)
    if not cleaned:
        return ""
    sentence = _pick_constraint_clause(cleaned)
    if not sentence:
        return ""
    if _is_mostly_ascii(sentence):
        return sentence if sentence.endswith((".", "!", "?")) else f"{sentence}."
    sentence = _ensure_requirement_style(sentence)
    if len(sentence) > 180:
        sentence = sentence[:177].rstrip() + "..."
    return sentence


def _validation_sentence(constraint: str) -> str:
    base = constraint.strip().rstrip(".")
    if not base:
        return ""
    upper = base.upper()
    if "암호" in base or "SSL" in upper or "TLS" in upper:
        return "개인정보 및 인증정보 송수신 구간의 암호화 적용 여부를 점검한다."
    if "권한" in base or "접근" in base:
        return "권한 없는 사용자의 접근 차단 여부와 인가된 권한별 기능 수행 여부를 검증한다."
    if "로그" in base or "이력" in base:
        return "주요 처리 이력과 오류 로그의 저장 및 조회 가능 여부를 점검한다."
    if "응답" in base or "성능" in base:
        return "정의된 성능 기준에 따라 응답시간과 처리량을 측정하여 기준 충족 여부를 확인한다."
    if "백업" in base or "복구" in base:
        return "백업 및 복구 절차 수행 후 데이터 복구 가능 여부를 검증한다."
    if "API" in upper or "연계" in base:
        return "외부 연계 및 API 호출의 인증, 오류 처리, 응답 형식 기준 충족 여부를 점검한다."
    if "표준" in base or "호환" in base or "접근성" in base:
        return "관련 표준과 호환성 기준 준수 여부를 점검한다."
    return f"{base} 여부를 점검한다."


def _build_rag_note(
    constraints: list[str],
    validation_criteria: list[str],
    constraint_results: list[dict[str, Any]],
    validation_results: list[dict[str, Any]],
) -> str:
    if not constraints and not validation_criteria:
        return ""
    reasons: list[str] = []
    if constraints:
        reasons.append("관련 비기능/RAG 근거에서 법적 또는 기술적 조건이 확인되어 제약사항에 반영함")
    if validation_criteria:
        if validation_results:
            reasons.append("검수/품질측정 근거가 확인되어 검수기준에 반영함")
        else:
            reasons.append("제약사항을 구현 후 확인 가능한 품질 기준으로 변환하여 검수기준에 반영함")
    source_ids = _evidence_source_ids(_merge_result_lists(constraint_results, validation_results))
    suffix = f" 참고 근거: {', '.join(source_ids[:3])}." if source_ids else ""
    return f"RAG 보강 근거: {'; '.join(reasons)}.{suffix}"


def _clean_evidence_text(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    text = re.sub(r"^[A-Z]{2,5}-\d{2,4}\s*[-:]\s*", "", text)
    return text


def _pick_constraint_clause(text: str) -> str:
    clauses = re.split(r"(?<=[.!?。])\s+|[•ㅇ○]\s*|\n+| - ", text)
    priority_keywords = [
        "보안",
        "암호",
        "SSL",
        "TLS",
        "개인정보",
        "권한",
        "접근",
        "로그",
        "성능",
        "응답",
        "품질",
        "표준",
        "인터페이스",
        "API",
        "데이터",
        "백업",
        "복구",
        "연계",
        "호환",
        "검수",
    ]
    candidates = [clause.strip(" .") for clause in clauses if len(clause.strip()) >= 12]
    for clause in candidates:
        if any(keyword.lower() in clause.lower() for keyword in priority_keywords):
            return clause
    return candidates[0] if candidates else ""


def _ensure_requirement_style(text: str) -> str:
    text = text.strip().rstrip(".")
    if _is_mostly_ascii(text):
        return text if text.endswith((".", "!", "?")) else f"{text}."
    if re.search(r"(해야 한다|하여야 한다|되어야 한다|한다|함)$", text):
        return f"{text}."
    return f"{text}해야 한다."


def _normalize_constraints(value: Any) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in _as_list(value):
        constraint = _constraint_sentence(item)
        if constraint and constraint not in seen:
            normalized.append(constraint)
            seen.add(constraint)
        if len(normalized) >= 3:
            break
    return normalized


def _normalize_validation_criteria(value: Any, constraints: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in _as_list(value):
        criterion = _clean_validation_text(item)
        if criterion and criterion not in seen:
            normalized.append(criterion)
            seen.add(criterion)
    if not normalized:
        normalized = constraints_to_validation_criteria(constraints)
    return normalized[:3]


def _clean_validation_text(text: str) -> str:
    text = _clean_evidence_text(text).rstrip(".")
    if not text:
        return ""
    if len(text) > 180:
        text = text[:177].rstrip() + "..."
    if _is_mostly_ascii(text):
        return f"{text}."
    if not re.search(r"(확인한다|점검한다|검증한다|측정한다|테스트한다)$", text):
        text = f"{text} 여부를 점검한다"
    return text


def _clean_note_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    if len(text) > 240:
        text = text[:237].rstrip() + "..."
    return text


def _append_note(existing: str, addition: str) -> str:
    existing = _clean_note_text(existing)
    addition = _clean_note_text(addition)
    if not addition:
        return existing
    if not existing:
        return addition
    if addition in existing:
        return existing
    return f"{existing} / {addition}"


def _is_mostly_ascii(text: str) -> bool:
    letters = re.findall(r"[A-Za-z가-힣]", text)
    if not letters:
        return False
    ascii_letters = [letter for letter in letters if letter.isascii()]
    return len(ascii_letters) / len(letters) >= 0.8


def _is_blocked_evidence(text: str) -> bool:
    blocked = [
        "하도급",
        "계약",
        "대금",
        "제안서 작성",
        "입찰",
        "사업관리",
        "차수",
        "보고서",
        "지체상금",
        "용역",
        "과업",
    ]
    lowered = text.lower()
    return any(term.lower() in lowered for term in blocked)


def _as_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def _merge_unique(*values: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in values:
        for value in group:
            text = str(value).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            merged.append(text)
    return merged
