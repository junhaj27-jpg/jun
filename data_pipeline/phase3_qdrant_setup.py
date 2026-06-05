import json
import uuid
from pathlib import Path
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue

from phase1_config import CONFIG, get_embedding, get_embeddings, get_qdrant

EXCLUDED_DOCUMENT_CATEGORIES = {"RFP"}

# ─────────────────────────────────────────────
# 컬렉션 생성
# ─────────────────────────────────────────────
def setup_collections(force_rebuild: bool = True):
    qdrant = get_qdrant()
    existing = [c.name for c in qdrant.get_collections().collections]
    
    for collection_name in [CONFIG["rfp_collection"], CONFIG["req_collection"]]:
        if collection_name in existing and force_rebuild:
            qdrant.delete_collection(collection_name)
            print(f" 🗑️  '{collection_name}' 삭제")
        
        qdrant.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=CONFIG["vector_dim"], distance=Distance.COSINE),
        )
        print(f" ✅ '{collection_name}' 생성 완료")

# ─────────────────────────────────────────────
# output/chunks/*.jsonl 일괄 적재 (RFP 제외)
# ─────────────────────────────────────────────
def ingest_jsonl_folder(folder_path: str):
    print(f"\n📂 [JSONL 적재] {folder_path} 폴더 내 비-RFP 파일 처리 중...")
    qdrant = get_qdrant()
    
    for jsonl_file in Path(folder_path).glob("*.jsonl"):
        print(f"  → 처리 중: {jsonl_file.name}")
        rows_by_collection = {
            CONFIG["rfp_collection"]: [],
            CONFIG["req_collection"]: [],
        }
        skipped = 0

        with open(jsonl_file, "r", encoding="utf-8") as f:
            for line in f:
                data = json.loads(line)
                text = data.get("page_content", "")
                metadata = data.get("metadata", {})

                if metadata.get("document_category") in EXCLUDED_DOCUMENT_CATEGORIES:
                    skipped += 1
                    continue

                target_col = (
                    CONFIG["req_collection"]
                    if metadata.get("chunk_type") == "REQUIREMENT"
                    else CONFIG["rfp_collection"]
                )

                rows_by_collection[target_col].append((text, metadata))

        if skipped:
            print(f"    ⏭️ RFP 청크 {skipped}개 제외")

        for target_col, rows in rows_by_collection.items():
            if not rows:
                continue

            texts = [text for text, _ in rows]
            vectors = get_embeddings(texts)
            points = [
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload={**metadata, "text": text}
                )
                for (text, metadata), vector in zip(rows, vectors)
            ]

            qdrant.upsert(collection_name=target_col, points=points)
            print(f"    ✅ {target_col}에 {len(points)}개 저장 완료")

def search_knowledge(query_text: str, doc_type_filter: str = None, top_k: int = 5):
    qdrant = get_qdrant()
    vector = get_embedding(query_text)

    query_filter = None

    if doc_type_filter:
        query_filter = Filter(
            must=[
                FieldCondition(
                    key="doc_type",
                    match=MatchValue(value=doc_type_filter)
                )
            ]
        )

    results = []
    existing = {c.name for c in qdrant.get_collections().collections}
    for collection_name in [CONFIG["rfp_collection"], CONFIG["req_collection"]]:
        if collection_name not in existing:
            continue
        results.extend(qdrant.query_points(
            collection_name=collection_name,
            query=vector,
            query_filter=query_filter,
            limit=top_k
        ).points)

    results = sorted(results, key=lambda p: p.score or 0, reverse=True)[:top_k]

    return [p.payload.get("text", "") for p in results]

def search_rfp(query_text: str, doc_type_filter: str = None, top_k: int = 5):
    """하위 호환용 별칭. 실제로는 RFP를 제외한 참고 지식 컬렉션을 검색합니다."""
    return search_knowledge(query_text, doc_type_filter=doc_type_filter, top_k=top_k)

def search_requirements(query_text: str, top_k: int = 5):
    qdrant = get_qdrant()
    vector = get_embedding(query_text)

    results = qdrant.query_points(
        collection_name=CONFIG["req_collection"],
        query=vector,
        limit=top_k
    ).points   # ⭐ 핵심

    return [p.payload.get("text", "") for p in results]
# ─────────────────────────────────────────────
# 실행 진입점
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print(" [PHASE 3] Qdrant 비-RFP 지식 베이스 통합 구축")
    print("=" * 55)
    
    # 1. 컬렉션 초기화
    setup_collections(force_rebuild=True)
    
    # 2. JSONL 파일 일괄 적재 (현재 가지고 있는 데이터 활용)
    if Path("output/chunks").exists():
        ingest_jsonl_folder("output/chunks")

    print("\n🎉 Phase 3 완료! 비-RFP 데이터가 Qdrant로 적재되었습니다.")
    print("다음 단계: python phase4_agent1.py")
