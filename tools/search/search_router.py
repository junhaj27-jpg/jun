from typing import Any

from tools.result import ToolResult, error_result, success_result
from tools.search.rag_search_tool import QdrantSearchClient, rag_search
from tools.search.search_schema import SearchRequest, SearchTarget
from tools.search.web_search_tool import WebSearchProvider, web_search


def search(
    query: str | dict[str, Any] | SearchRequest,
    *,
    search_targets: SearchTarget = "RAG",
    filters: dict[str, Any] | None = None,
    top_k: int = 5,
    query_vector: list[float] | None = None,
    collection: str | None = None,
    rag_client: QdrantSearchClient | None = None,
    web_provider: WebSearchProvider | None = None,
) -> ToolResult:
    request_meta: dict[str, Any] = {}
    if isinstance(query, (dict, SearchRequest)):
        try:
            request = query if isinstance(query, SearchRequest) else SearchRequest(**query)
        except Exception as exc:
            return error_result("SEARCH_REQUEST_INVALID", str(exc))
        query = request.query
        search_targets = request.search_targets
        filters = request.filters
        top_k = request.top_k
        query_vector = request.query_vector
        collection = request.collection
        request_meta = {
            "project_sn": request.project_sn,
            "docs_cd": request.docs_cd,
            "agent_name": request.agent_name,
            "search_intent": request.search_intent,
        }

    target = search_targets.upper()
    if target == "NONE":
        return success_result(
            {
                "query": query,
                "search_type": "NONE",
                "results": [],
                "normalized_results": [],
                "request": request_meta,
            }
        )
    if target == "RAG":
        result = rag_search(
            query,
            query_vector=query_vector,
            filters=filters,
            top_k=top_k,
            collection=collection,
            client=rag_client,
        )
        return _with_request_meta(result, request_meta)
    if target == "WEB":
        result = web_search(query, filters=filters, top_k=top_k, provider=web_provider)
        return _with_request_meta(result, request_meta)
    if target == "BOTH":
        rag_result = rag_search(
            query,
            query_vector=query_vector,
            filters=filters,
            top_k=top_k,
            collection=collection,
            client=rag_client,
        )
        web_result = web_search(
            query,
            filters=filters,
            top_k=top_k,
            provider=web_provider,
        )
        if not rag_result["success"] and not web_result["success"]:
            return error_result(
                "SEARCH_BOTH_FAILED",
                "RAG 및 Web 검색이 모두 실패했습니다.",
                {"rag": rag_result["error"], "web": web_result["error"]},
            )
        normalized_results = []
        raw_results = []
        for result in (rag_result, web_result):
            if result["success"]:
                normalized_results.extend(result["data"]["normalized_results"])
                raw_results.extend(result["data"].get("results", []))
        return success_result(
            {
                "query": query,
                "search_type": "BOTH",
                "results": raw_results,
                "normalized_results": normalized_results,
                "request": request_meta,
            }
        )
    return error_result("INVALID_SEARCH_TARGET", f"허용되지 않은 검색 대상: {search_targets}")


def _with_request_meta(result: ToolResult, request_meta: dict[str, Any]) -> ToolResult:
    if result["success"]:
        result["data"]["request"] = request_meta
    return result
