"""
[PHASE 3] Qdrant 다중 컬렉션 지식 베이스 구축 (v2)

변경 사항 (v1 → v2):
  - 컬렉션 2개로 분리
      rfp_knowledge_base     : RFP + 가이드/법령 (Agent 1 Mode B, Agent 2)
      requirements_knowledge_base : 과거 요구사항 명세서 (Agent 1 Mode A)
  - doc_type 메타데이터 태깅 추가
      scope        현재 프로젝트 RFP  (Agent 1 Mode B 시 최우선 참조)
      rule         보안/기술 법령    (절대 기준)
      pattern      유사 사업 RFP    (참고만, 충돌 시 무시)
      generated_req 과거 요구사항명세서 (Agent 1 Mode A 시 패턴 참조)
  - ingest 함수를 PDF/DOCX/HWP 어떤 형식이든 받을 수 있도록 수정

실행 방법:
  python phase3_qdrant_setup.py

의존성:
  phase1_config.py, phase1a_doc_reader.py
"""

import json
import os
import uuid
from pathlib import Path

from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue

from phase1_config import CONFIG, get_embedding, get_qdrant
from phase1a_doc_reader import read_document, chunk_document


# ─────────────────────────────────────────────
# 컬렉션 생성
# ─────────────────────────────────────────────
def setup_collections(force_rebuild: bool = False):
    """
    Qdrant에 두 개의 컬렉션을 생성합니다.
    
    Args:
        force_rebuild: True면 기존 컬렉션 삭제 후 재생성
    """
    qdrant = get_qdrant()
    existing = [c.name for c in qdrant.get_collections().collections]
    
    for collection_name in [CONFIG["rfp_collection"], CONFIG["req_collection"]]:
        if collection_name in existing:
            if not force_rebuild:
                print(f"  ✅ '{collection_name}' 이미 존재 (재생성: force_rebuild=True)")
                continue
            qdrant.delete_collection(collection_name)
            print(f"  🗑️  '{collection_name}' 삭제")
        
        qdrant.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=CONFIG["vector_dim"],  # 768
                distance=Distance.COSINE,
            ),
        )
        print(f"  ✅ '{collection_name}' 생성 완료")


# ─────────────────────────────────────────────
# [컬렉션 1] RFP 및 가이드 적재
# ─────────────────────────────────────────────
def ingest_rfp_document(file_path: str, doc_type: str = "scope"):
    """
    RFP 또는 가이드/법령 문서를 rfp_knowledge_base에 적재합니다.
    PDF, DOCX, HWP, HWPX 모두 지원합니다.
    
    Args:
        file_path: 문서 파일 경로
        doc_type: 문서 유형
            "scope"   : 현재 프로젝트 RFP (기본값)
            "rule"    : 보안/기술 법령 가이드
            "pattern" : 유사 사업 RFP (참고용)
    
    사용 예시:
        # 현재 RFP (최우선 기준)
        ingest_rfp_document("data/RFP_원본.pdf", doc_type="scope")
        
        # 보안 가이드라인 (절대 규칙)
        ingest_rfp_document("가이드/소프트웨어_보안약점_진단가이드.pdf", doc_type="rule")
        
        # 유사 프로젝트 RFP (참고용)
        ingest_rfp_document("RFP/다른사업_제안요청서.hwp", doc_type="pattern")
    """
    if doc_type not in ("scope", "rule", "pattern"):
        raise ValueError(f"doc_type은 'scope', 'rule', 'pattern' 중 하나여야 합니다. 입력값: {doc_type}")
    
    print(f"\n📥 [{doc_type.upper()}] 적재 시작: {Path(file_path).name}")
    
    # 텍스트 추출
    text = read_document(file_path)
    print(f"   → {len(text):,}자 추출")
    
    # 청킹
    chunks = chunk_document(text, max_chars=400)
    print(f"   → {len(chunks)}개 청크 분할")
    
    # 임베딩 + 포인트 구성
    print("   → 임베딩 계산 중...")
    points = []
    for i, chunk in enumerate(chunks, 1):
        points.append(PointStruct(
            id=str(uuid.uuid4()),
            vector=get_embedding(chunk),
            payload={
                "text":        chunk,
                "doc_type":    doc_type,
                "source":      Path(file_path).name,
                "chunk_index": i,
            },
        ))
        if i % 10 == 0 or i == len(chunks):
            print(f"   {i}/{len(chunks)} 처리 완료")
    
    # Qdrant 저장
    get_qdrant().upsert(collection_name=CONFIG["rfp_collection"], points=points)
    print(f"   ✅ rfp_knowledge_base에 {len(points)}개 청크 저장 완료")


# ─────────────────────────────────────────────
# [컬렉션 2] 과거 요구사항 명세서 적재
# ─────────────────────────────────────────────
def ingest_requirements_json(json_path: str, project_name: str = ""):
    """
    Agent 1이 생성한 요구사항 명세서 JSON을 requirements_knowledge_base에 적재합니다.
    Agent 1 Mode A가 새 회의록을 처리할 때 과거 패턴을 참고하는 용도로 사용됩니다.
    
    사용 시점:
      - 프로젝트 완료 후 검증된 명세서를 아카이브할 때 적재
      - 현재 진행 중인 프로젝트 명세서는 적재하지 마세요 (미검증 데이터)
    
    Args:
        json_path    : 요구사항 명세서 JSON 파일 경로
        project_name : 프로젝트명 (메타데이터용, 생략 시 파일명 사용)
    """
    print(f"\n📥 [GENERATED_REQ] 적재 시작: {Path(json_path).name}")
    
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    requirements = data.get("requirements", [])
    if not requirements:
        print("   ⚠️  요구사항이 비어있습니다. 건너뜁니다.")
        return
    
    source = project_name or Path(json_path).stem
    points = []
    
    for req in requirements:
        # 각 요구사항을 하나의 청크로 저장 (ID 단위 검색을 위해)
        text_repr = (
            f"[{req.get('requirement_id','')}] {req.get('requirement_name','')}\n"
            f"유형: {req.get('requirement_type','')} | 우선순위: {req.get('priority','')}\n"
            f"설명: {req.get('description','')}\n"
            f"검수기준: {'; '.join(req.get('validation_criteria', []))}"
        )
        points.append(PointStruct(
            id=str(uuid.uuid4()),
            vector=get_embedding(text_repr),
            payload={
                "text":             text_repr,
                "doc_type":         "generated_req",
                "source":           source,
                "requirement_id":   req.get("requirement_id", ""),
                "requirement_name": req.get("requirement_name", ""),
            },
        ))
    
    get_qdrant().upsert(collection_name=CONFIG["req_collection"], points=points)
    print(f"   ✅ requirements_knowledge_base에 {len(points)}개 요구사항 저장 완료")


# ─────────────────────────────────────────────
# 검색 함수 (에이전트가 import하여 사용)
# ─────────────────────────────────────────────
def search_rfp(query: str, doc_type_filter: str = None) -> list[str]:
    """
    rfp_knowledge_base에서 관련 조항을 검색합니다.
    
    Args:
        query          : 검색 질의 텍스트
        doc_type_filter: 특정 doc_type만 검색 (None이면 전체 검색)
                         "scope", "rule", "pattern" 중 선택
    Returns:
        유사도 상위 k개 텍스트 리스트
    
    사용 예시:
        # 전체 검색 (RFP + 가이드 + 유사 RFP)
        results = search_rfp("로그인 보안 요구사항")
        
        # 현재 RFP 범위만 검색 (임의 확장 방지)
        results = search_rfp("인증 방식", doc_type_filter="scope")
        
        # 보안 규칙만 검색
        results = search_rfp("암호화", doc_type_filter="rule")
    """
    qdrant = get_qdrant()
    
    query_filter = None
    if doc_type_filter:
        query_filter = Filter(
            must=[FieldCondition(key="doc_type", match=MatchValue(value=doc_type_filter))]
        )
    
    results = qdrant.search(
        collection_name=CONFIG["rfp_collection"],
        query_vector=get_embedding(query),
        query_filter=query_filter,
        limit=CONFIG["top_k"],
    )
    return [hit.payload["text"] for hit in results]


def search_requirements(query: str) -> list[str]:
    """
    requirements_knowledge_base에서 유사한 과거 요구사항을 검색합니다.
    Agent 1 Mode A (회의록 → 명세서 생성)에서 패턴 참고용으로 사용합니다.
    
    Args:
        query: 검색 질의 (회의록의 특정 기능 관련 텍스트)
    Returns:
        유사도 상위 k개 요구사항 텍스트 리스트
    """
    results = get_qdrant().search(
        collection_name=CONFIG["req_collection"],
        query_vector=get_embedding(query),
        limit=CONFIG["top_k"],
    )
    return [hit.payload["text"] for hit in results]


# ─────────────────────────────────────────────
# 실행 진입점
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  [PHASE 3] Qdrant 지식 베이스 구축")
    print("=" * 55)
    
    # 컬렉션 생성 (force_rebuild=True: 기존 데이터 삭제 후 재생성)
    print("\n▶ Step 1: 컬렉션 생성")
    setup_collections(force_rebuild=True)
    
    # ─ RFP 적재 예시 ─────────────────────────
    print("\n▶ Step 2: 문서 적재")
    
    # [필수] 현재 프로젝트 RFP → doc_type: "scope"
    # 실제 파일 경로로 변경하세요
    rfp_candidates = [
        "data/RFP_원본.pdf",
        "data/RFP_원본.txt",
        "data/RFP_원본.docx",
    ]
    rfp_loaded = False
    for rfp_path in rfp_candidates:
        if os.path.exists(rfp_path):
            ingest_rfp_document(rfp_path, doc_type="scope")
            rfp_loaded = True
            break
    if not rfp_loaded:
        print("  ⚠️  RFP 파일 없음. 먼저 phase2_sample_data.py를 실행하세요.")
    
    # [선택] 보안/기술 가이드라인 → doc_type: "rule"
    # 예: ingest_rfp_document("강제규정/소프트웨어_보안약점_진단가이드.pdf", doc_type="rule")
    print("\n  💡 가이드라인 적재 방법 (실제 파일 준비 후 아래 주석 해제):")
    print("     ingest_rfp_document('강제규정/소프트웨어_보안약점_진단가이드.pdf', doc_type='rule')")
    print("     ingest_rfp_document('기술/표준프레임워크_적용가이드_v5.0.pdf',   doc_type='rule')")
    
    # [선택] 유사 사업 RFP → doc_type: "pattern"
    # 예: ingest_rfp_document("RFP/다른사업_제안요청서.hwp", doc_type="pattern")
    print("     ingest_rfp_document('RFP/다른사업_제안요청서.hwp',              doc_type='pattern')")
    
    # [선택] 과거 요구사항 명세서 → requirements_knowledge_base
    past_req_path = "output/agent1_requirements.json"
    if os.path.exists(past_req_path):
        print(f"\n▶ Step 3: 과거 요구사항 명세서 적재 ({past_req_path})")
        ingest_requirements_json(past_req_path, project_name="과거_프로젝트")
    else:
        print("\n▶ Step 3: 과거 요구사항 명세서 없음 (Agent 1 실행 후 수동 적재 가능)")
    
    # 검색 테스트
    print("\n▶ 검색 테스트")
    if rfp_loaded:
        print("  [전체 검색] '실시간 갱신' 관련 조항:")
        for r in search_rfp("실시간 갱신 주기"):
            print(f"    → {r[:80]}...")
    
    print("\n🎉 Phase 3 완료! 다음 단계: python phase4_agent1.py")
