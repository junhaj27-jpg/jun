"""
[PHASE 0 - 완료] 표준 요구사항 스키마 정의
- 이 파일은 이미 완성되어 있습니다.
- 모든 다른 파일에서 이 스키마를 import하여 사용합니다.
"""
from pydantic import BaseModel, Field
from typing import List, Optional


class CanonicalRequirement(BaseModel):
    requirement_id: str = Field(..., description="요구사항 고유 ID (예: REQ-001)")
    requirement_name: str = Field(..., description="요구사항명")
    requirement_type: str = Field(..., description="'기능' 또는 '비기능'")
    description: str = Field(..., description="요구사항의 상세 설명 본문")
    source: List[str] = Field(..., description="출처 문서 (예: 회의록_20260523, RFP_3p)")
    constraints: List[str] = Field(default=[], description="제약사항 목록")
    priority: str = Field(..., description="중요도: '상' 또는 '중' 또는 '하'")
    validation_criteria: List[str] = Field(..., description="검수 및 승인 기준 목록")
    note: Optional[str] = Field(None, description="비고 사항 (없으면 null)")


class RequirementDocument(BaseModel):
    requirements: List[CanonicalRequirement]
