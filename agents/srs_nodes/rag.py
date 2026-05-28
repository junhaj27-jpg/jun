# nodes/rag.py
from agents.srs_state import State
from rag.srs_rag_service import RAGService

rag = RAGService()

def rag_node(state: State) -> dict:
    query = state["cleaned_minutes"][:500]
    results  = rag.query(query.strip(), doc_types=["scope", "rule", "pattern"])
    return {"rag_context": rag.format_context(results)}
