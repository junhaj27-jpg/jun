"""ERD 테이블에 Mermaid 분할 생성을 위한 그래프 메타데이터를 추가합니다."""

from typing import Any


DOMAIN_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("USER", ("user", "usr", "member", "customer", "고객", "사용자", "회원")),
    ("AUTH", ("auth", "role", "permission", "login", "권한", "역할", "인증", "인가", "메뉴")),
    ("DOCUMENT", ("document", "docs", "doc", "문서", "산출물")),
    ("FILE", ("file", "attach", "첨부", "파일")),
    ("RAG", ("rag", "chunk", "embedding", "vector", "knowledge", "검색증강", "청크", "임베딩", "벡터")),
    ("AGENT", ("agent", "workflow", "tool", "에이전트", "워크플로우")),
    ("MODEL", ("model", "llm", "sllm", "prompt", "모델", "프롬프트")),
    ("API", ("api", "interface", "연계", "인터페이스")),
    ("MONITORING", ("monitor", "log", "audit", "trace", "history", "hist", "로그", "감사", "추적", "이력")),
    ("COMMON", ("code", "config", "common", "job", "batch", "코드", "설정", "공통", "작업", "배치")),
)

TABLE_TYPE_IMPORTANCE = {
    "MASTER": 80,
    "DETAIL": 55,
    "MAPPING": 45,
    "VERSION": 40,
    "HISTORY": 35,
    "LOG": 30,
    "APPROVAL": 70,
    "JOB": 50,
    "JOB_STEP": 35,
    "FILE": 60,
    "CODE": 65,
    "CONFIG": 65,
}


def enrich_table_metadata(
    tables: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """테이블별 domain_group, relation_count, importance_score를 채웁니다."""

    relation_counts = _relation_counts(tables, relationships)
    enriched: list[dict[str, Any]] = []
    for table in tables:
        item = dict(table)
        table_name = _table_name(item)
        relation_count = relation_counts.get(table_name, 0)
        domain_group = str(item.get("domain_group") or _infer_domain_group(item))
        item["domain_group"] = domain_group
        item["relation_count"] = int(item.get("relation_count") or relation_count)
        item["importance_score"] = int(
            item.get("importance_score") or _importance_score(item, relation_count)
        )
        enriched.append(item)
    return enriched


def _relation_counts(tables: list[dict[str, Any]], relationships: list[dict[str, Any]]) -> dict[str, int]:
    names = {_table_name(table) for table in tables}
    counts = {name: 0 for name in names if name}
    for relation in relationships:
        parent = _relation_parent(relation)
        child = _relation_child(relation)
        if parent in counts:
            counts[parent] += 1
        if child in counts:
            counts[child] += 1
    return counts


def _importance_score(table: dict[str, Any], relation_count: int) -> int:
    table_type = str(table.get("table_type") or "").upper()
    base = TABLE_TYPE_IMPORTANCE.get(table_type, 50)
    source_bonus = min(len(table.get("source_requirement_ids") or []) * 5, 20)
    return base + relation_count * 10 + source_bonus


def _infer_domain_group(table: dict[str, Any]) -> str:
    text = " ".join(
        str(value or "")
        for value in (
            table.get("table_name"),
            table.get("physical_name"),
            table.get("logical_name"),
            table.get("table_korean_name"),
            table.get("description"),
            table.get("reason"),
        )
    ).lower()
    for domain, keywords in DOMAIN_KEYWORDS:
        if any(keyword.lower() in text for keyword in keywords):
            return domain
    return "COMMON"


def _table_name(table: dict[str, Any]) -> str:
    return str(table.get("table_name") or table.get("physical_name") or table.get("name") or "")


def _relation_parent(relation: dict[str, Any]) -> str:
    return str(relation.get("parent_table") or relation.get("to_table") or relation.get("to") or relation.get("target") or "")


def _relation_child(relation: dict[str, Any]) -> str:
    return str(relation.get("child_table") or relation.get("from_table") or relation.get("from") or relation.get("source") or "")
