# nodes/rag.py
from state import State
from services.rag_service import RAGService

rag = RAGService()

def rag_node(state: State) -> dict:
    rfp_text = " ".join(r.get("description", "")[:200] for r in state["rfp"])
    query    = " ".join(state["topics"]) + " " + rfp_text
    results  = rag.query(query.strip(), doc_types=["scope", "rule", "pattern"])
    return {"rag_context": rag.format_context(results)}