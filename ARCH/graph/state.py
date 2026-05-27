import operator
from typing import TypedDict, Dict, Any, List
from typing_extensions import TypedDict
from pydantic import BaseModel, Field

# 1. 원본 요구사항 수신용 Pydantic 스키마 (사용자 정의 스키마 완벽 일치)
class RequirementItem(BaseModel):
    requirement_id: str = Field(..., description="요구사항 고유 ID (예: SSR-F01001)")
    requirement_name: str = Field(..., description="요구사항 명")
    requirement_type: str = Field(..., description="요구사항 구분 (기능/비기능)")
    description: str = Field(..., description="요구사항 상세 내용 및 비즈니스 로직")
    source: List[str] = Field(..., description="요구사항 출처 및 페이지 정보")
    constraints: List[str] = Field(..., description="시스템 및 비즈니스 제약조건")
    priority: str = Field(..., description="우선순위 (상/중/하)")
    validation_criteria: List[str] = Field(..., description="테스트 및 검증 기준")
    note: str = Field(default="", description="기타 참고사항 및 특이사항")

class RequirementDocument(BaseModel):
    requirements: List[RequirementItem]


class AgentState(TypedDict):
    # 기존 입력 및 분석 데이터 필드
    requirements_doc: str
    user_infra_spec: Dict[str, Any]
    analyzed_reqs: List[Dict[str, Any]]
    extracted_infra: Dict[str, Any]
    
    # ─── [변경 사항] 기능 분리를 위한 핵심 전용 필드 ───
    report_specs: str         # 텍스트/표 기반 요구사항 명세 섹션
    mermaid_script: str       # 순수 Mermaid 다이어그램 스크립트
    image_path: str           # 변환 완료된 아키텍처 이미지 파일 경로
    # ──────────────────────────────────────────────────
    
    # 검증 및 루프 제어 필드
    validation_result: Dict[str, Any]
    retry_count: int

