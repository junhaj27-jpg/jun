# nodes/rag.py
import os

from agents.srs_state import State
from rag.srs_rag_service import RAGService

rag = RAGService()

def rag_node(state: State) -> dict:
    use_rag = os.getenv("SRS_RAG_ENABLED", "false").strip().lower() in {"1", "true", "yes", "y"}
    if not use_rag:
        return {"rag_context": "[RAG 검색 생략: SRS_RAG_ENABLED=false]"}

    rfp_text = " ".join(r.get("description", "")[:200] for r in state["rfp"])
    query    = " ".join(state["topics"]) + " " + rfp_text
    results  = rag.query(query.strip(), doc_types=["scope", "rule", "pattern"])
    return {"rag_context": rag.format_context(results)}
