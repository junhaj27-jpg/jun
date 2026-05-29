import logging

from qdrant_client.models import FieldCondition, Filter, MatchValue

from rag.qdrant_config import (
    REQUIREMENT_RAG_TOP_K,
    REQUIREMENT_REFERENCE_COLLECTION,
    REQUIREMENT_SOURCES_COLLECTION,
    get_client,
    get_embedding,
)

logger = logging.getLogger(__name__)

_COL_RFP = REQUIREMENT_SOURCES_COLLECTION
_COL_REQ = REQUIREMENT_REFERENCE_COLLECTION
_TOP_K = REQUIREMENT_RAG_TOP_K


class RAGService:
    def query(
        self,
        text: str,
        doc_types: list[str] | None = None,
        top_k: int = _TOP_K,
    ) -> list[dict]:
        try:
            vector = get_embedding(text)
        except Exception as e:
            logger.error("rag: embedding failed -> %s", e)
            return []
        rfp_hits = self._search(_COL_RFP, vector, doc_types, top_k)
        req_hits = self._search(_COL_REQ, vector, None, top_k)
        combined = sorted(rfp_hits + req_hits, key=lambda x: x["score"], reverse=True)
        return combined[: top_k * 2]

    def format_context(self, results: list[dict]) -> str:
        if not results:
            return "[RAG 검색 결과 없음]"
        return "\n\n".join(
            f"[{r.get('doc_type', '').upper()}] {r.get('source', '')}\n{r.get('text', '')}"
            for r in results
        )

    def _search(self, collection: str, vector, doc_types, top_k: int):
        try:
            hits = get_client().query_points(
                collection_name=collection,
                query=vector,
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
