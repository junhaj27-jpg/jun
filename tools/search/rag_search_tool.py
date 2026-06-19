from typing import Any, Protocol

from config.settings import Settings, get_settings
from tools.result import ToolResult, error_result, success_result
from tools.search.result_normalizer import normalize_results


class QdrantSearchClient(Protocol):
    def query_points(self, **kwargs: Any) -> Any: ...


def rag_search(
    query: str,
    *,
    query_vector: list[float] | None = None,
    filters: dict[str, Any] | None = None,
    top_k: int = 5,
    collection: str | None = None,
    client: QdrantSearchClient | None = None,
    settings: Settings | None = None,
) -> ToolResult:
    if not query.strip():
        return error_result("RAG_INVALID_QUERY", "query는 비어 있을 수 없습니다.")
    if not query_vector:
        return error_result(
            "RAG_QUERY_VECTOR_REQUIRED",
            "Qdrant 검색에는 query_vector가 필요합니다.",
        )

    settings = settings or get_settings()
    selected_collection = collection or settings.alpled_reference_collection

    try:
        qdrant = client or _create_qdrant_client(settings)
        response = qdrant.query_points(
            collection_name=selected_collection,
            query=query_vector,
            query_filter=_to_qdrant_filter(filters),
            limit=top_k,
            with_payload=True,
        )
        points = list(getattr(response, "points", response))
        normalized = normalize_results("RAG", query, points)
        if not normalized["success"]:
            return normalized
        return success_result(
            {
                "search_type": "RAG",
                "query": query,
                "results": [_to_rag_result(point) for point in points],
                "normalized_results": normalized["data"]["normalized_results"],
            }
        )
    except ImportError as exc:
        return error_result("RAG_CLIENT_UNAVAILABLE", str(exc))
    except Exception as exc:
        return error_result(
            "RAG_SEARCH_FAILED",
            str(exc),
            {"collection": selected_collection},
        )


def _create_qdrant_client(settings: Settings) -> QdrantSearchClient:
    from qdrant_client import QdrantClient

    kwargs = {"url": settings.resolved_qdrant_url}
    if settings.qdrant_api_key:
        kwargs["api_key"] = settings.qdrant_api_key
    return QdrantClient(**kwargs)


def _to_qdrant_filter(filters: dict[str, Any] | None) -> Any:
    if not filters:
        return None
    try:
        from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

        conditions = []
        for key, value in filters.items():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            if isinstance(value, (list, tuple, set)):
                values = [item for item in value if item is not None and str(item).strip()]
                if not values:
                    continue
                conditions.append(FieldCondition(key=key, match=MatchAny(any=values)))
            else:
                conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
        return Filter(must=conditions) if conditions else None
    except Exception:
        return filters


def _to_rag_result(point: Any) -> dict[str, Any]:
    item = point if isinstance(point, dict) else vars(point)
    payload = item.get("payload") or item.get("metadata") or {}
    return {
        "content": item.get("content") or item.get("text") or payload.get("content") or payload.get("text") or "",
        "score": item.get("score"),
        "metadata": payload,
    }
