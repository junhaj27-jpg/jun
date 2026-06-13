from collections.abc import Callable
from typing import Any

from tools.result import ToolResult, error_result, success_result
from tools.search.result_normalizer import normalize_results


WebSearchProvider = Callable[[str, int, dict[str, Any] | None], list[Any]]


def web_search(
    query: str,
    *,
    top_k: int = 5,
    filters: dict[str, Any] | None = None,
    provider: WebSearchProvider | None = None,
) -> ToolResult:
    if not query.strip():
        return error_result("WEB_SEARCH_INVALID_QUERY", "query는 비어 있을 수 없습니다.")
    if provider is None:
        return error_result(
            "WEB_SEARCH_PROVIDER_REQUIRED",
            "Web 검색 provider가 아직 연결되지 않았습니다.",
        )

    try:
        raw_results = provider(query, top_k, filters)
        normalized = normalize_results("WEB", query, raw_results)
        if not normalized["success"]:
            return normalized
        return success_result(
            {
                "search_type": "WEB",
                "query": query,
                "results": [_to_web_result(item) for item in raw_results],
                "normalized_results": normalized["data"]["normalized_results"],
            }
        )
    except Exception as exc:
        return error_result("WEB_SEARCH_FAILED", str(exc))


def _to_web_result(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        item = vars(item) if hasattr(item, "__dict__") else {"snippet": str(item)}
    return {
        "title": item.get("title", ""),
        "url": item.get("url") or item.get("link") or "",
        "snippet": item.get("snippet") or item.get("content") or item.get("text") or "",
        "source": item.get("source", ""),
        "published_at": item.get("published_at", ""),
    }
