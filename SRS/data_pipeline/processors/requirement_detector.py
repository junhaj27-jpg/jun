"""
[수정된 requirement_detector.py]

버그 수정:
  ❌ 150자 미만 청크 일괄 False → 중요한 짧은 규정도 삭제됨
  ❌ 표 파이프(|) 형식에서 "하여야 한다" 패턴 미검출
  ❌ 규정/가이드 문서도 "하여야 한다" 없으면 산출물외기타 처리

개선:
  - 최소 길이 150 → 30자
  - 파이프 제거 후 텍스트 재검사
  - knowledge_role 기반 역할 오버라이드
  - detect_requirement_signal() 함수 보존 (__init__.py 호환)
"""
import re
from typing import Dict, Any, List

REQUIREMENT_PATTERNS = [
    "하여야 한다", "해야 한다", "지원해야 한다", "가능해야 한다", "제공해야 한다",
    "구축해야 한다", "적용해야 한다", "처리할 수 있어야 한다", "조회할 수 있어야 한다",
    "준수하여야 한다", "관리하여야 한다", "반영하여야 한다",
    "연계하여야 한다", "연계해야 한다", "연동해야 한다", "도입하여야 한다", "도입해야 한다",
    "포함하여야 한다", "포함해야 한다", "보장하여야 한다", "보장해야 한다",
    "유지하여야 한다", "유지해야 한다", "방지하여야 한다", "방지해야 한다",
    "제출하여야 한다", "제출해야 한다", "보고하여야 한다", "보고해야 한다",
    "설치하여야 한다", "구현하여야 한다", "확인하여야 한다",
]

REQUIREMENT_HEADERS = [
    "요구사항번호", "요구사항고유번호", "요구사항명", "요구사항분류", "상세설명", "세부내용"
]

# 이 knowledge_role을 가진 문서는 패턴 없어도 유효 청크로 처리
ALWAYS_VALID_ROLES = {"VALIDATION_RULE", "WRITING_STANDARD", "TECH_REFERENCE"}


def detect_requirement_signal(text: str) -> bool:
    """
    __init__.py 호환을 위해 보존.
    단순히 요구사항 패턴 포함 여부만 반환 (True/False).
    """
    if not text or len(text.strip()) < 30:
        return False

    text_clean = re.sub(r"\|", " ", text)  # 표 파이프 제거 후 검사

    for pattern in REQUIREMENT_PATTERNS:
        if pattern in text or pattern in text_clean:
            return True

    no_space = text.replace(" ", "").replace("·", "")
    if "세부내용" in no_space or "상세설명" in no_space:
        for header in REQUIREMENT_HEADERS:
            if header in no_space:
                return True

    return False


def analyze_requirement(text: str, knowledge_role: str = "") -> Dict[str, Any]:
    """
    청크 텍스트를 분석하여 요구사항 여부 + 산출물 매핑 반환.

    Args:
        text          : 청크 텍스트
        knowledge_role: 문서 역할 (VALIDATION_RULE 등이면 패턴 없어도 유효)
    """
    result: Dict[str, Any] = {
        "is_requirement": False,
        "matched_signals": [],
        "mapped_artifacts": [],
    }

    if not text:
        return result

    # ✅ 수정: 최소 길이 150 → 30자
    if len(text.strip()) < 30:
        result["mapped_artifacts"].append("산출물외기타")
        return result

    # ✅ 수정: 표 파이프 제거 후 패턴 재검사
    text_no_pipe = re.sub(r"\|", " ", text)

    for pattern in REQUIREMENT_PATTERNS:
        if pattern in text or pattern in text_no_pipe:
            result["matched_signals"].append(pattern)

    if result["matched_signals"]:
        result["is_requirement"] = True

    # 헤더 기반 탐지
    if not result["is_requirement"]:
        no_space = text.replace(" ", "").replace("·", "")
        if "세부내용" in no_space or "상세설명" in no_space:
            for header in REQUIREMENT_HEADERS:
                if header in no_space:
                    result["is_requirement"] = True
                    result["matched_signals"].append(f"HEADER:{header}")

    # ✅ 수정: 역할 기반 오버라이드 — 규정/가이드 문서는 무조건 유효
    if not result["is_requirement"] and knowledge_role in ALWAYS_VALID_ROLES:
        result["is_requirement"] = True
        result["matched_signals"].append(f"ROLE_OVERRIDE:{knowledge_role}")

    # 산출물 매핑
    from processors.category_mapper import ARTIFACT_CLASSIFICATION
    lower = text.lower()
    for artifact, keywords in ARTIFACT_CLASSIFICATION.items():
        for kw in keywords:
            if kw.lower() in lower:
                result["mapped_artifacts"].append(artifact)
                break

    if not result["mapped_artifacts"]:
        result["mapped_artifacts"].append("일반참고문서")

    result["mapped_artifacts"] = sorted(list(set(result["mapped_artifacts"])))
    return result