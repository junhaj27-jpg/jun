from typing import Any

from tools.result import ToolResult, error_result, success_result
from tools.search.search_schema import SearchResult


def normalize_results(
    search_type: str,
    query: str,
    results: list[Any],
) -> ToolResult:
    try:
        source = search_type.upper()
        if source not in {"RAG", "WEB"}:
            return error_result(
                "SEARCH_NORMALIZE_INVALID_SOURCE",
                f"허용되지 않은 검색 출처: {search_type}",
            )

        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(results):
            item = _to_mapping(item)
            if isinstance(item, dict):
                payload = item.get("payload") or item.get("metadata") or {}
                title = item.get("title") or payload.get("title") or ""
                url = item.get("url") or item.get("link") or payload.get("url")
                source_path = item.get("source_path") or payload.get("source_path")
                page = item.get("page") or payload.get("page")
                normalized.append(
                    SearchResult(
                        source_kind=source,
                        id=item.get("id", index),
                        title=title,
                        content=item.get("content")
                        or item.get("text")
                        or item.get("snippet")
                        or payload.get("content")
                        or payload.get("text")
                        or "",
                        url=url,
                        score=item.get("score"),
                        metadata=payload,
                        citation=_build_citation(source, title, url, source_path, page),
                    ).model_dump()
                )
            else:
                normalized.append(
                    SearchResult(
                        source_kind=source,
                        id=index,
                        content=str(item),
                    ).model_dump()
                )
        return success_result(
            {"query": query, "normalized_results": normalized}
        )
    except Exception as exc:
        return error_result("SEARCH_NORMALIZE_FAILED", str(exc))


def _to_mapping(item: Any) -> Any:
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if hasattr(item, "dict"):
        return item.dict()
    if hasattr(item, "__dict__"):
        return vars(item)
    return item


def _build_citation(
    source: str,
    title: str,
    url: str | None,
    source_path: str | None,
    page: Any,
) -> str:
    if source == "WEB" and url:
        return url
    if source == "RAG":
        base = source_path or title
        if base and page:
            return f"{base}#page={page}"
        return base or ""
    return ""
