"""도메인별 보조 사전을 적용합니다."""

from typing import Any


DOMAIN_OBJECT_RULES: dict[str, tuple[tuple[str, str, str, str], ...]] = {
    "AI_PLATFORM": (
        ("AI 모델", "MASTER", "AI 모델 설정 관리 대상"),
        ("모델", "MASTER", "AI 모델 설정 관리 대상"),
        ("프롬프트", "MASTER", "프롬프트 템플릿 관리 대상"),
        ("Agent", "MASTER", "Agent 설정 및 실행 관리 대상"),
        ("에이전트", "MASTER", "Agent 설정 및 실행 관리 대상"),
        ("RAG", "JOB", "RAG 처리 작업 관리 대상"),
        ("청킹", "DETAIL", "문서 청크 처리 상세 데이터"),
        ("chunking", "DETAIL", "문서 청크 처리 상세 데이터"),
        ("임베딩", "INDEX", "벡터DB 색인 매핑 대상"),
        ("embedding", "INDEX", "벡터DB 색인 매핑 대상"),
        ("벡터", "INDEX", "벡터DB 색인 매핑 대상"),
    ),
    "DATA_PLATFORM": (
        ("데이터소스", "MASTER", "원천 데이터 수집 대상"),
        ("데이터셋", "MASTER", "분석/활용 데이터셋 관리 대상"),
        ("카탈로그", "MASTER", "데이터 카탈로그 관리 대상"),
        ("메타데이터", "DETAIL", "데이터 자산 메타데이터 관리"),
        ("품질", "HISTORY", "데이터 품질 점검 이력 관리"),
        ("수집", "JOB", "데이터 수집 작업 관리"),
        ("적재", "JOB", "데이터 적재 작업 관리"),
    ),
    "FINANCE": (
        ("계좌", "MASTER", "금융 계좌 정보 관리 대상"),
        ("거래", "HISTORY", "금융 거래 이력 관리"),
        ("대출", "MASTER", "대출 정보 관리 대상"),
        ("심사", "APPROVAL", "금융 심사 승인 흐름 관리"),
    ),
    "CRM": (
        ("고객", "MASTER", "고객 정보 관리 대상"),
        ("상담", "HISTORY", "상담 이력 관리"),
        ("캠페인", "MASTER", "마케팅 캠페인 관리 대상"),
    ),
    "ERP": (
        ("전표", "MASTER", "회계 전표 관리 대상"),
        ("구매", "MASTER", "구매 업무 관리 대상"),
        ("재고", "MASTER", "재고 정보 관리 대상"),
    ),
    "GROUPWARE": (
        ("결재", "APPROVAL", "전자 결재 흐름 관리"),
        ("게시판", "MASTER", "게시판 정보 관리 대상"),
        ("일정", "MASTER", "일정 정보 관리 대상"),
    ),
}


def apply_domain_dictionary(
    requirements: list[dict[str, Any]],
    domain_info: dict[str, Any],
) -> list[dict[str, Any]]:
    """도메인 키워드가 실제 요구사항에 있을 때만 보조 객체를 반환합니다."""

    matched_domains = domain_info.get("matched_domains") or []
    additions: list[dict[str, Any]] = []
    for requirement in requirements:
        text = f"{requirement['requirement_name']}\n{requirement['detail']}"
        for domain in matched_domains:
            for keyword, object_type, reason in DOMAIN_OBJECT_RULES.get(domain, ()):
                if keyword.lower() not in text.lower():
                    continue
                additions.append(
                    {
                        "requirement_id": requirement["requirement_id"],
                        "requirement_type": requirement["requirement_type"],
                        "requirement_name": requirement["requirement_name"],
                        "name": _canonical_name(keyword),
                        "object_type": object_type,
                        "reason": reason,
                        "domain": domain,
                    }
                )
    return _dedupe(additions)


def _canonical_name(keyword: str) -> str:
    aliases = {
        "모델": "AI 모델",
        "에이전트": "Agent",
        "청킹": "청크",
        "chunking": "청크",
        "embedding": "임베딩",
        "벡터": "임베딩",
        "수집": "작업",
        "적재": "작업",
        "심사": "승인",
        "결재": "승인",
    }
    return aliases.get(keyword, keyword)


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    deduped = []
    for item in items:
        key = (item["requirement_id"], item["name"], item["object_type"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped
