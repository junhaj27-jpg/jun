# 수정 파이프라인용 RAG
# 기존 요구사항 텍스트로 쿼리
from state import ModifyState
from services.rag_service import RAGService

rag = RAGService()

def rag_modify_node(state: ModifyState) -> dict:
    # 기존 요구사항 + 수정 지시를 합쳐서 검색
    req_text = " ".join(
        r.get("description", "")[:100]
        for r in state["existing_reqs"][:5]   # 상위 5개만
    )
    query   = state["instruction"] + " " + req_text
    results = rag.query(query.strip(), doc_types=["scope", "rule"])
    return {"rag_context": rag.format_context(results)}