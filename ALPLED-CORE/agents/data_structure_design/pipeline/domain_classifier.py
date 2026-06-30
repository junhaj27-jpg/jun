"""요구사항 텍스트에서 업무 도메인을 판별합니다."""

from typing import Any


DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "AI_PLATFORM": ("AI 모델", "인공지능", "LLM", "프롬프트", "Agent", "에이전트", "RAG", "임베딩", "벡터DB", "모델 추론"),
    "ERP": ("회계", "전표", "구매", "재고", "인사", "급여", "자산", "예산"),
    "CRM": ("고객", "상담", "캠페인", "영업", "리드", "VOC", "마케팅"),
    "SCM": ("공급망", "발주", "입고", "출고", "물류", "배송", "창고"),
    "MES": ("생산", "공정", "설비", "작업지시", "품질검사", "불량"),
    "GROUPWARE": ("결재", "게시판", "메일", "일정", "회의", "전자문서"),
    "HOSPITAL": ("환자", "진료", "처방", "검사", "병동", "의료", "보험청구"),
    "PORTAL": ("포털", "게시글", "콘텐츠", "댓글", "배너", "공지"),
    "DATA_PLATFORM": ("데이터", "수집", "적재", "ETL", "DW", "마트", "카탈로그", "품질", "메타데이터"),
    "FINANCE": ("계좌", "거래", "대출", "상환", "심사", "금융", "이자", "한도"),
}


def classify_domain(requirements: list[dict[str, Any]]) -> dict[str, Any]:
    text = "\n".join(
        f"{item.get('requirement_name', '')}\n{item.get('detail', '')}"
        for item in requirements
    )
    scores = {
        domain: sum(1 for keyword in keywords if keyword.lower() in text.lower())
        for domain, keywords in DOMAIN_KEYWORDS.items()
    }
    matched = [domain for domain, score in scores.items() if score > 0]
    primary = max(matched, key=lambda domain: scores[domain]) if matched else "GENERAL"
    return {
        "primary_domain": primary,
        "matched_domains": matched,
        "scores": scores,
    }
