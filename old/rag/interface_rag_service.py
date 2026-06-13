import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

INTERFACE_UIUX_COLLECTION = os.getenv(
    "INTERFACE_UIUX_COLLECTION",
    "interface_uiux_reference",
)
INTERFACE_RAG_TOP_K = int(os.getenv("INTERFACE_RAG_TOP_K", "5"))


class InterfaceRAGService:
    def query(
        self,
        text: str,
        *,
        doc_types: list[str] | None = None,
        top_k: int = INTERFACE_RAG_TOP_K,
    ) -> list[dict[str, Any]]:
        text = (text or "").strip()
        if not text:
            return []
        if not self._collection_exists(INTERFACE_UIUX_COLLECTION):
            logger.warning("interface rag collection not found: %s", INTERFACE_UIUX_COLLECTION)
            return []
        try:
            from rag.qdrant_config import get_client, get_embedding

            vector = get_embedding(text)
            hits = get_client().query_points(
                collection_name=INTERFACE_UIUX_COLLECTION,
                query=vector,
                query_filter=_build_filter(doc_types),
                limit=top_k,
                with_payload=True,
            ).points
        except Exception as exc:
            logger.error("interface rag query failed: %s", exc)
            return []

        return [
            {
                "text": (hit.payload or {}).get("text", ""),
                "doc_type": (hit.payload or {}).get("doc_type", ""),
                "source": (hit.payload or {}).get("source_name", ""),
                "section": (hit.payload or {}).get("section", ""),
                "title": (hit.payload or {}).get("title", ""),
                "page": (hit.payload or {}).get("page", ""),
                "score": round(hit.score or 0, 4),
            }
            for hit in hits
        ]

    def format_context(self, results: list[dict[str, Any]]) -> str:
        if not results:
            return ""
        blocks = []
        for item in results:
            title = item.get("title") or item.get("section") or item.get("doc_type")
            source = item.get("source") or "UIUX guideline"
            page = item.get("page")
            page_text = f" p.{page}" if page else ""
            blocks.append(
                f"[{item.get('doc_type', 'ui_reference')}] {source}{page_text} / {title}\n"
                f"{item.get('text', '')}"
            )
        return "\n\n".join(blocks)

    def _collection_exists(self, collection_name: str) -> bool:
        try:
            from rag.qdrant_config import get_client

            return collection_name in {c.name for c in get_client().get_collections().collections}
        except Exception as exc:
            logger.error("interface rag collection check failed: %s", exc)
            return False


def _build_filter(doc_types: list[str] | None):
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    conditions = [FieldCondition(key="is_active", match=MatchValue(value=True))]
    if doc_types:
        return Filter(
            must=conditions,
            should=[
                FieldCondition(key="doc_type", match=MatchValue(value=doc_type))
                for doc_type in doc_types
            ],
        )
    return Filter(must=conditions)
