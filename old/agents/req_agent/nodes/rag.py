import logging
from state import State
from services.rag_service import RAGService

logger = logging.getLogger(__name__)
rag    = RAGService()

def rag_node(state: State) -> dict:
    query   = state["cleaned_minutes"][:500]
    results = rag.query(query, doc_types=["scope", "rule", "pattern"])
    logger.debug("rag: %d results", len(results))
    return {"rag_context": rag.format_context(results)}
