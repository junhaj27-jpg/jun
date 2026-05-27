"""
[수정된] processors/metadata_builder.py

변경사항:
  ✅ parsed_requirement 딕셔너리를 metadata에 플랫하게 저장
     → original_req_id, req_name, definition, sub_details, deliverables 직접 접근 가능
  ✅ parsed_requirement가 비어있어도 에러 없이 처리
"""
from typing import Dict, List, Optional, Any


def generate_chunk_title(text: str, max_length: int = 60) -> str:
    if not text:
        return "EMPTY_CHUNK"
    first_line = text.split("\n")[0].strip()
    return first_line[:max_length] + "..." if len(first_line) > max_length else first_line


def determine_chunk_type(requirement_signal: bool) -> str:
    return "REQUIREMENT" if requirement_signal else "GENERAL"

def build_metadata(
    *,
    chunk_id: str,
    text: str,
    source_name: str,
    source_path: str,
    page: int,
    document_category: str,
    document_type: str,
    knowledge_role: str,
    section_title: str,
    chunk_index: int,
    requirement_analysis: Dict,
    domain_analysis: Dict,
    parsed_requirement: Dict[str, Any],
    priority: str = "NORMAL",
    version: str = "1.0",
    language: str = "ko",
    project_name: Optional[str] = None,
) -> Dict:
    chunk_title    = generate_chunk_title(text)
    is_requirement = requirement_analysis.get("is_requirement", False)
    matched_signals = requirement_analysis.get("matched_signals", [])
    target_artifacts = domain_analysis.get("target_artifacts", ["일반참고문서"])
    business_domains = domain_analysis.get("business_domains", ["GENERAL"])
    chunk_type = determine_chunk_type(is_requirement)

    metadata = {
        "chunk_id":          chunk_id,
        "chunk_index":       chunk_index,
        "text":              text,
        "full_text_content": text,  # ✅ 추가: 데이터 유실 방지용 안전장치

        # 문서 분류
        "document_category":  document_category,
        "document_type":      document_type,
        "knowledge_role":     knowledge_role,

        # 위치 정보
        "section":            section_title,
        "title":              chunk_title,
        "page":               page,

        # 요구사항 분석
        "requirement_signal":  is_requirement,
        "requirement_signals": matched_signals,
        "requirement_domain":  business_domains,
        "applies_to":          target_artifacts,
        "chunk_type":          chunk_type,

        # ✅ 핵심 수정: 원본 RFP 요구사항 데이터를 플랫하게 저장
        # (parsed_requirement가 비어있으면 None으로 처리)
        "original_req_id":    parsed_requirement.get("original_req_id"),
        "original_req_name":  parsed_requirement.get("requirement_name"),
        "original_req_type":  parsed_requirement.get("requirement_type"),
        "definition":         parsed_requirement.get("definition"),
        "sub_details":        parsed_requirement.get("sub_details", []),
        "deliverables":       parsed_requirement.get("deliverables", []),
        "req_constraints":    parsed_requirement.get("constraints", []),

        # 출처 추적성
        "source_name":        source_name,
        "source_path":        source_path,

        # 거버넌스
        "priority":           priority,
        "version":            version,
        "language":           language,
        "is_active":          True,
    }

    if project_name:
        metadata["project_name"] = project_name  # ✅ 수정: chunk_title 대신 올바른 project_name 대입

    return metadata
# def build_metadata(
#     *,
#     chunk_id: str,
#     text: str,
#     source_name: str,
#     source_path: str,
#     page: int,
#     document_category: str,
#     document_type: str,
#     knowledge_role: str,
#     section_title: str,
#     chunk_index: int,
#     requirement_analysis: Dict,
#     domain_analysis: Dict,
#     parsed_requirement: Dict[str, Any],
#     priority: str = "NORMAL",
#     version: str = "1.0",
#     language: str = "ko",
#     project_name: Optional[str] = None,
# ) -> Dict:
#     chunk_title    = generate_chunk_title(text)
#     is_requirement = requirement_analysis.get("is_requirement", False)
#     matched_signals = requirement_analysis.get("matched_signals", [])
#     target_artifacts = domain_analysis.get("target_artifacts", ["일반참고문서"])
#     business_domains = domain_analysis.get("business_domains", ["GENERAL"])
#     chunk_type = determine_chunk_type(is_requirement)

#     metadata = {
#         "chunk_id":           chunk_id,
#         "chunk_index":        chunk_index,
#         "text":               text,

#         # 문서 분류
#         "document_category":  document_category,
#         "document_type":      document_type,
#         "knowledge_role":     knowledge_role,

#         # 위치 정보
#         "section":            section_title,
#         "title":              chunk_title,
#         "page":               page,

#         # 요구사항 분석
#         "requirement_signal":  is_requirement,
#         "requirement_signals": matched_signals,
#         "requirement_domain":  business_domains,
#         "applies_to":          target_artifacts,
#         "chunk_type":          chunk_type,

#         # ✅ 핵심 수정: 원본 RFP 요구사항 데이터를 플랫하게 저장
#         # (parsed_requirement가 비어있으면 None으로 처리)
#         "original_req_id":    parsed_requirement.get("original_req_id"),
#         "original_req_name":  parsed_requirement.get("requirement_name"),
#         "original_req_type":  parsed_requirement.get("requirement_type"),
#         "definition":         parsed_requirement.get("definition"),
#         "sub_details":        parsed_requirement.get("sub_details", []),
#         "deliverables":       parsed_requirement.get("deliverables", []),
#         "req_constraints":    parsed_requirement.get("constraints", []),

#         # 출처 추적성
#         "source_name":        source_name,
#         "source_path":        source_path,

#         # 거버넌스
#         "priority":           priority,
#         "version":            version,
#         "language":           language,
#         "is_active":          True,
#     }

#     if project_name:
#         metadata["project_name"] = chunk_title

#     return metadata
