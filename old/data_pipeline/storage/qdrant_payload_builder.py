from typing import Dict, List, Any, Union
# 💡 Qdrant 공식 라이브러리에서 대량 삽입용 표준 포인트 구조체를 임포트합니다.
from qdrant_client.models import PointStruct
from schemas.chunk_schema import ChunkData

def build_qdrant_payload(
    *,
    chunk_id: str,
    page_content: str,
    metadata: Dict[str, Any],
    embedding: List[float]
) -> Dict[str, Any]:
    """
    [기존 로직 유지] 일반 딕셔너리 포맷의 Qdrant 페이로드 데이터를 빌드합니다.
    JSON 저장이나 다른 API 전송용으로 유용합니다.
    """
    return {
        "id": chunk_id,
        "vector": embedding,
        "payload": {
            "page_content": page_content,
            "metadata": metadata
        }
    }


def build_qdrant_point(
    chunk: ChunkData,
    embedding: List[float]
) -> PointStruct:
    """
    [실전형 확장 엔진] 
    전처리 파이프라인의 결과물인 ChunkData 객체와 임베딩 벡터를 결합하여,
    Qdrant DB에 다이렉트로 대량 적재(Upsert) 가능한 '공식 PointStruct 객체'를 빌드합니다.
    """
    # 1. ChunkData 스키마 내부의 메타데이터를 순수 딕셔너리로 직렬화
    meta_dict = chunk.metadata.to_dict()
    
    # 2. Qdrant 가 검색(Retrieval) 시 핵심 필드로 인지할 구조 세팅
    payload_data = {
        "page_content": chunk.page_content, # 벡터 검색과 매칭될 본문 텍스트
        "metadata": meta_dict
    }
    
    # 3. Qdrant Python Client 공식 규격 포인트 객체 반환
    return PointStruct(
        id=chunk.chunk_id,      # UUID 문자열 형태 수용
        vector=embedding,       # 임베딩 모델이 뽑아낸 고차원 수치 배열
        payload=payload_data    # 산출물 태그(applies_to) 등이 포함된 고밀도 메타데이터
    )
