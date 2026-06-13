# 비기능 요구사항 검색에 사용할 RAG 질의를 생성합니다.

from typing import Any


NON_FUNCTIONAL_CATEGORIES = ["보안", "성능", "품질", "인터페이스", "데이터"]


def build_rag_query(item: dict[str, Any]) -> str:
    name = item.get("requirement_name") or item.get("req_name") or ""
    description = item.get("description") or item.get("detail_text") or ""
    categories = ", ".join(NON_FUNCTIONAL_CATEGORIES)
    return f"{name} {description} 관련 {categories} 정책 표준 제약사항"
