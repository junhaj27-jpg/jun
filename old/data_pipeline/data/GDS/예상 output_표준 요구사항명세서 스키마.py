from pydantic import BaseModel, Field
from typing import List, Optional

class CanonicalRequirement(BaseModel):
    requirement_id: str = Field(..., description="요구사항 고유 ID (예: REQ-001)")
    requirement_name: str = Field(..., description="요구사항명")
    requirement_type: str = Field(..., description="기능 또는 비기능")
    description: str = Field(..., description="요구사항의 상세 설명 본문")
    source: List[str] = Field(..., description="출처 문서 (예: 회의록_20260523, RFP_3p)")
    constraints: List[str] = Field(default=[], description="제약사항 목록")
    priority: str = Field(..., description="중요도 (상/중/하)")
    validation_criteria: List[str] = Field(..., description="검수 및 승인 기준")
    note: Optional[str] = Field(None, description="비고 사항")

class RequirementDocument(BaseModel):
    requirements: List[CanonicalRequirement]