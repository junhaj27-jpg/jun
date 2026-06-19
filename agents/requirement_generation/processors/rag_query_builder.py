from __future__ import annotations

from typing import Any

from tools.llm.llm_client import LLMClient
from tools.llm.response_parser import parse_json_response
from tools.llm.send_api import send_parallel


NON_FUNCTIONAL_CATEGORIES = [
    "보안",
    "성능",
    "품질",
    "인터페이스",
    "데이터",
    "법적 조건",
    "기술 조건",
    "검수 기준",
]


def build_rag_query(item: dict[str, Any]) -> str:
    """Backward compatible constraint-oriented query."""

    return build_rag_query_set(item)["constraints"]


def build_rag_query_set(item: dict[str, Any]) -> dict[str, str]:
    name = item.get("requirement_name") or item.get("req_name") or ""
    description = (
        item.get("requirement_detail")
        or item.get("description")
        or item.get("detail_text")
        or ""
    )
    base = f"{name} {description}".strip()
    categories = ", ".join(NON_FUNCTIONAL_CATEGORIES)
    return {
        "constraints": f"{base} 관련 {categories} 제약사항 법적 조건 기술 조건",
        "validation_criteria": f"{base} 관련 검수기준 인수기준 품질측정 정량 정성 평가 기준",
    }


def build_rag_queries_parallel(
    items: list[dict[str, Any]],
    *,
    llm_client: LLMClient | None = None,
    max_workers: int = 4,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Backward compatible list of constraint-oriented queries."""

    query_sets, warnings = build_rag_query_sets_parallel(
        items,
        llm_client=llm_client,
        max_workers=max_workers,
    )
    return [query_set["constraints"] for query_set in query_sets], warnings


def build_rag_query_sets_parallel(
    items: list[dict[str, Any]],
    *,
    llm_client: LLMClient | None = None,
    max_workers: int = 4,
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Build separate RAG queries for constraints and validation criteria."""

    warnings: list[dict[str, Any]] = []
    fallback = [build_rag_query_set(item) for item in items]
    if llm_client is None or not items:
        return fallback, warnings

    requests = [
        {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "기능 요구사항과 관련된 비기능 요구사항 및 참조 가이드를 찾기 위한 RAG query를 JSON으로 반환하세요. "
                        "constraints는 요구사항이 수행되기 위해 필요한 법적 또는 기술적인 조건을 찾는 검색어입니다. "
                        "validation_criteria는 요구사항 구현 후 품질을 정량적 또는 정성적으로 측정할 수 있는 검수 기준을 찾는 검색어입니다. "
                        "검색어에는 기능명, 핵심 행위, 보안/성능/품질/인터페이스/데이터 범주 중 관련 범주를 포함하세요. "
                        "반환 형식: {\"constraints\": \"...\", \"validation_criteria\": \"...\"}"
                    ),
                },
                {"role": "user", "content": str(item)},
            ]
        }
        for item in items
    ]
    result = send_parallel(requests, client=llm_client, max_workers=max_workers)
    if not result["success"]:
        warnings.append({"code": "REQUIREMENT_QUERY_BUILDER_FAILED", "message": result["error"]["message"]})
        return fallback, warnings

    query_sets: list[dict[str, str]] = []
    for index, item_result in enumerate(result["data"]):
        query_set = dict(fallback[index])
        if item_result and item_result["success"]:
            parsed = parse_json_response(item_result["data"])
            if parsed["success"]:
                value = parsed["data"]
                if isinstance(value, dict):
                    constraints = str(
                        value.get("constraints")
                        or value.get("constraint_query")
                        or value.get("query")
                        or ""
                    ).strip()
                    validation = str(
                        value.get("validation_criteria")
                        or value.get("validation_query")
                        or value.get("acceptance_query")
                        or ""
                    ).strip()
                    if constraints:
                        query_set["constraints"] = constraints
                    if validation:
                        query_set["validation_criteria"] = validation
                elif isinstance(value, str):
                    query = value.strip()
                    if query:
                        query_set["constraints"] = query
                        query_set["validation_criteria"] = query
        query_sets.append(query_set)
    return query_sets, warnings
