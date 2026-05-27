from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

@dataclass
class MetadataSchema:
    """
    [5대 산출물 추출 시스템 표준 메타데이터 스키마]
    Qdrant Payload 필드 타입을 강제하고 누락을 원천 차단하는 핵심 명세서입니다.
    """

    chunk_id: str
    document_category: str      # RFP, 강제 규정, 기술, GDS 등
    document_type: str          # PDF, DOCX, TEXT 등
    knowledge_role: str         # 지식 역할 (ENGINEERING_SPEC 등)
    section: str                # 상위 장/절 제목
    title: str                  # 청크 대표 타이틀
    page: int                   # 페이지 번호
    chunk_index: int           # 문서 내 청크 순번
    
    # 요구사항 및 5대 산출물 매핑 정보 (핵심)
    requirement_signal: bool    # 의무 요구사항 여부 (True/False)
    requirement_signals: List[str] # 매칭된 세부 서술어 패턴들
    requirement_domain: List[str]  # 상세 업무 도메인 분류 (SYSTEM_AUTH 등)
    chunk_type: str            # REQUIREMENT / GENERAL
    applies_to: List[str]          # ★ 기여할 5대 핵심 개발 산출물 목록 태그
    
    # 출처 추적성 (Traceability) 및 거버넌스 정보
    source_name: str
    source_path: str
    text: Optional[str] = None
    full_text_content: Optional[str] = None
    priority: str = "NORMAL"
    version: str = "1.0"
    language: str = "ko"
    is_active: bool = True
    project_name: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MetadataSchema":
        """
        딕셔너리 형태의 데이터를 전처리 엔진 규격 스키마 객체로 강제 매핑합니다.
        Key가 빠져있을 경우 오프라인 환경에 맞는 기본값(Default)을 보장합니다.
        """
        return cls(
            chunk_id=data.get("chunk_id", ""),
            document_category=data.get("document_category", "기타"),
            document_type=data.get("document_type", "UNKNOWN"),
            knowledge_role=data.get("knowledge_role", "GENERAL"),
            section=data.get("section", "UNKNOWN_SECTION"),
            title=data.get("title", ""),
            page=data.get("page", 1),
            chunk_index=data.get("chunk_index", 0),
            requirement_signal=data.get("requirement_signal", False),
            # requirement_detector의 수정한 다중 시그널 리스트 수용
            requirement_signals=data.get("requirement_signals", []), 
            requirement_domain=data.get("requirement_domain", []),
            chunk_type=data.get("chunk_type", "GENERAL"),
            # domain_detector의 수정한 5대 산출물 매핑 태그 수용
            applies_to=data.get("applies_to", ["일반참고문서"]),
            source_name=data.get("source_name", ""),
            source_path=data.get("source_path", ""),
            text=data.get("text"), # 추가
            full_text_content=data.get("full_text_content"), # 추가
            priority=data.get("priority", "NORMAL"),
            version=data.get("version", "1.0"),
            language=data.get("language", "ko"),
            is_active=data.get("is_active", True),
            project_name=data.get("project_name")
        )

    def to_dict(self) -> Dict[str, Any]:
        """Qdrant 페이로드 삽입 및 JSON 직렬화용 순수 딕셔너리 변환"""
        return asdict(self)
