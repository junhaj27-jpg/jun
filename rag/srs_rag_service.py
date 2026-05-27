import logging

from qdrant_client.models import FieldCondition, Filter, MatchValue

from rag.qdrant_config import (
    REQUIREMENT_EXAMPLES_COLLECTION,
    REQUIREMENT_RAG_TOP_K,
    REQUIREMENT_REFERENCE_COLLECTION,
    REQUIREMENT_SOURCES_COLLECTION,
    get_client,
    get_embedding,
)

logger = logging.getLogger(__name__)

_COLLECTIONS = [
    REQUIREMENT_REFERENCE_COLLECTION,
    REQUIREMENT_SOURCES_COLLECTION,
    REQUIREMENT_EXAMPLES_COLLECTION,
]
_TOP_K = REQUIREMENT_RAG_TOP_K


class RAGService:
    def query(
        self,
        text: str,
        doc_types: list[str] | None = None,
        top_k: int = _TOP_K,
        collections: list[str] | None = None,
    ) -> list[dict]:
        target_collections = collections or _COLLECTIONS
        hits = []
        for collection in target_collections:
            hits.extend(self._search(collection, text, doc_types, top_k))
        return sorted(hits, key=lambda x: x["score"], reverse=True)[: top_k * 2]

    def format_context(self, results: list[dict]) -> str:
        if not results:
            return "[RAG 검색 결과 없음]"
        return "\n\n".join(
            f"[{r.get('doc_type', '').upper()}] {r.get('source', '')}\n{r.get('text', '')}"
            for r in results
        )

    def _search(self, collection: str, text: str, doc_types, top_k: int):
        try:
            hits = get_client().query_points(
                collection_name=collection,
                query=get_embedding(text),
                query_filter=_build_filter(doc_types),
                limit=top_k,
                with_payload=True,
            ).points
            logger.debug("rag: %s -> %d hits", collection, len(hits))
            return [
                {
                    "text": h.payload.get("text", ""),
                    "doc_type": h.payload.get("doc_type", ""),
                    "source": h.payload.get("source_name", h.payload.get("source", "")),
                    "collection": collection,
                    "score": round(h.score, 4),
                }
                for h in hits
            ]
        except Exception as e:
            logger.error("rag: %s failed -> %s", collection, e)
            return []


def _build_filter(doc_types):
    if not doc_types:
        return None
    return Filter(
        should=[
            FieldCondition(key="doc_type", match=MatchValue(value=dt))
            for dt in doc_types
        ]
    )
