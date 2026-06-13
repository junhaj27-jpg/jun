from typing import Any

from common.text_utils import extract_keywords
from rag.base_rag_service import search_rag


def build_erd_rag_queries(requirement_json: dict[str, Any], meeting_text: str) -> list[str]:
    seeds = []
    for item in requirement_json.get("requirements", []):
        if not isinstance(item, dict):
            continue
        seeds.extend(
            [
                item.get("requirement_name", ""),
                item.get("description", ""),
                " ".join(item.get("validation_criteria", []) if isinstance(item.get("validation_criteria"), list) else []),
                " ".join(item.get("keywords", []) if isinstance(item.get("keywords"), list) else []),
            ]
        )
    seeds.append(meeting_text)
    keywords = extract_keywords(" ".join(str(seed or "") for seed in seeds), limit=36)

    queries = []
    if keywords:
        queries.append(" ".join(keywords[:12]))
        queries.append("테이블 컬럼명 표준 도메인 " + " ".join(keywords[:10]))
        queries.append("공공데이터베이스 표준화 명명 규칙 " + " ".join(keywords[:10]))
    return list(dict.fromkeys(query for query in queries if query.strip()))


def search_erd_standards(requirement_json: dict[str, Any], meeting_text: str) -> dict[str, Any]:
    queries = build_erd_rag_queries(requirement_json, meeting_text)
    context = {
        "domain": "public_data",
        "db_standard_manual": [],
        "public_standard_terms": [],
        "public_standard_words": [],
        "public_standard_domains": [],
    }
    if not queries:
        return context

    query = " ".join(queries)
    context["db_standard_manual"] = search_rag(
        query=query,
        domain="public_data",
        applies_to="erd",
        doc_type="db_standard_manual",
        limit=8,
    )
    context["public_standard_terms"] = search_rag(
        query=query,
        domain="public_data",
        applies_to="erd",
        doc_type="standard_term",
        limit=8,
    )
    context["public_standard_words"] = search_rag(
        query=query,
        domain="public_data",
        applies_to="erd",
        doc_type="standard_word",
        limit=8,
    )
    context["public_standard_domains"] = search_rag(
        query=query,
        domain="public_data",
        applies_to="erd",
        doc_type="standard_domain",
        limit=8,
    )
    return context


def build_erd_rag_context(requirement: dict[str, Any]) -> dict[str, Any]:
    requirement_json = {
        "requirements": [
            {
                "requirement_name": requirement.get("requirement_name", ""),
                "description": requirement.get("description", ""),
                "validation_criteria": requirement.get("validation_criteria", []),
                "keywords": [],
            }
        ]
    }
    context = search_erd_standards(requirement_json, "")
    context["domain"] = classify_domain(requirement)
    return context


def classify_domain(requirement: dict[str, Any]) -> str:
    text = " ".join(
        [
            requirement.get("requirement_name", ""),
            requirement.get("description", ""),
            " ".join(requirement.get("constraints", [])),
            " ".join(requirement.get("validation_criteria", [])),
        ]
    )
    finance_keywords = [
        "계좌", "이체", "입금", "출금", "은행", "금융", "결제",
        "잔액", "한도", "거래", "당좌예금", "수취", "자금",
        "금리", "대출", "예금", "채권", "기관", "결제망",
    ]
    if any(keyword in text for keyword in finance_keywords):
        return "finance"
    return "general"
