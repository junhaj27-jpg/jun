import os
from pathlib import Path
from typing import Optional

# 공공 표준 문서 타입 및 본문 스캔용 키워드 사전 (경로 탐지 실패 시 폴백용)
DOCUMENT_KEYWORDS = {
    "RFP": ["제안요청서", "RFP", "요구사항", "과업내용서", "기능요구"],
    "REGULATION": ["강제규정", "지침", "법령", "고시", "기준", "규정"],
    "TECH_GUIDE": ["기술가이드", "아키텍처 가이드", "매뉴얼", "설치지침서", "기술표준"],
    "GUIDE": ["요구사항 가이드", "가이드라인", "작성 가이드"],
    "GLOSSARY": ["용어사전", "용어집", "정의", "약어"],
    "GDS": ["GDS", "Global Design System", "디자인 표준"]
}

def detect_document_category(file_path: str) -> str:
    """
    [제공해주신 핵심 코드] 
    Path.parts를 사용해 원시 데이터(Raw) 폴더 구조를 기반으로 
    문서의 카테고리를 가장 정확하게 1차 분류합니다.
    """
    path_parts = Path(file_path).parts
    for part in path_parts:
        if part in [
            "RFP",
            "강제 규정",
            "기술",
            "요구사항 가이드",
            "용어사전",
            "GDS",
        ]:
            return part
    return "기타"

def classify_by_content(text: str) -> str:
    """
    [2차 방어 레이어] 경로에 카테고리 폴더명이 없을 경우(예: 임시 테스트 파일 등), 
    문서 상단 텍스트를 스캔하여 가장 유력한 카테고리를 추정합니다.
    """
    if not text:
        return "기타"
        
    head_text = text[:2000] # 상위 2000자 스캔
    type_scores = {doc_type: 0 for doc_type in DOCUMENT_KEYWORDS}
    
    for doc_type, keywords in DOCUMENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in head_text:
                type_scores[doc_type] += 1
                
    max_type = max(type_scores, key=type_scores.get)
    
    # 점수가 매칭된 게 있다면 한글 카테고리명으로 변환하여 반환
    if type_scores[max_type] > 0:
        mapping = {
            "RFP": "RFP", "REGULATION": "강제 규정", "TECH_GUIDE": "기술",
            "GUIDE": "요구사항 가이드", "GLOSSARY": "용어사전", "GDS": "GDS"
        }
        return mapping.get(max_type, "기타")
        
    return "기타"

def classify_document(file_path: str, full_text: Optional[str] = None) -> str:
    """
    [통합 엔트리 포인트] 
    1차로 제공해주신 경로 기반 분류를 가동하고, 
    만약 결과가 '기타'로 나오면 2차로 본문 내용을 분석하여 최종 문서 카테고리를 결정합니다.
    """
    # 1. 제공해주신 경로 기반 탐지 작동
    category = detect_document_category(file_path)
    if category != "기타":
        return category
    
    if "RFP" in file_path or "제안요청서" in file_path:
        return "RFP"
    
    # 2. 경로 탐지 실패 시 본문 기반 탐지 보완 작동
    if full_text:
        return classify_by_content(full_text)
        
    return "기타"
