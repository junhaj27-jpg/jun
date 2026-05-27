import json
from typing import Dict, Any

from qdrant_client.models import Filter, FieldCondition, MatchValue

from rag.qdrant_config import get_client, get_embedder, COLLECTION_NAME


def classify_domain(requirement: Dict[str, Any]) -> str:
    text = " ".join([
        requirement.get("requirement_name", ""),
        requirement.get("description", ""),
        " ".join(requirement.get("constraints", [])),
        " ".join(requirement.get("validation_criteria", [])),
    ])

    finance_keywords = [
        "계좌", "이체", "입금", "출금", "은행", "금융", "결제",
        "잔액", "한도", "거래", "당좌예금", "수취", "자금",
        "금리", "대출", "예금", "채권", "기관", "결제망"
    ]

    if any(keyword in text for keyword in finance_keywords):
        return "finance"
    return "general"


def search_rag(
    query: str,
    *,
    domain: str | None = None,
    applies_to: str | None = None,
    doc_type: str | None = None,
    chunk_type: str | None = None,
    limit: int = 5,
):
    client = get_client()
    embedder = get_embedder()

    query_vector = embedder.encode(query, normalize_embeddings=True).tolist()

    conditions = [
        FieldCondition(key="is_active", match=MatchValue(value=True))
    ]

    if domain:
        conditions.append(FieldCondition(key="domain", match=MatchValue(value=domain)))
    if doc_type:
        conditions.append(FieldCondition(key="doc_type", match=MatchValue(value=doc_type)))
    if chunk_type:
        conditions.append(FieldCondition(key="chunk_type", match=MatchValue(value=chunk_type)))

    result = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter=Filter(must=conditions),
        limit=limit * 3,
        with_payload=True,
    )

    rows = []
    for item in result.points:
        payload = item.payload or {}

        if applies_to and applies_to not in payload.get("applies_to", ""):
            continue

        rows.append({
            "score": item.score,
            "text": payload.get("text", ""),
            "metadata": payload,
        })

        if len(rows) >= limit:
            break

    return rows


def build_erd_rag_context(requirement: Dict[str, Any]) -> Dict[str, Any]:
    domain = classify_domain(requirement)

    query = " ".join([
        requirement.get("requirement_name", ""),
        requirement.get("description", ""),
        " ".join(requirement.get("constraints", [])),
        " ".join(requirement.get("validation_criteria", [])),
    ])

    context = {
        "domain": domain,
        "db_standard_manual": [],
        "public_standard_terms": [],
        "public_standard_words": [],
        "public_standard_domains": [],
    }

    context["db_standard_manual"] = search_rag(
        query=query,
        domain="public_data",
        applies_to="erd",
        doc_type="db_standard_manual",
        limit=8,
    )

    context["public_standard_terms"] = search_rag(
        query=query,
        domain="public_data",
        applies_to="erd",
        doc_type="standard_term",
        limit=8,
    )

    context["public_standard_words"] = search_rag(
        query=query,
        domain="public_data",
        applies_to="erd",
        doc_type="standard_word",
        limit=8,
    )

    context["public_standard_domains"] = search_rag(
        query=query,
        domain="public_data",
        applies_to="erd",
        doc_type="standard_domain",
        limit=8,
    )

    return context


def compact_rag_context(rag_context: Dict[str, Any], max_chars_per_group: int = 3500) -> Dict[str, Any]:
    compact = {}

    for key, value in rag_context.items():
        if key == "domain":
            compact[key] = value
            continue

        items = []
        total = 0

        for row in value:
            metadata = row.get("metadata", {})
            text = row.get("text", "")

            item = {
                "score": row.get("score"),
                "doc_type": metadata.get("doc_type"),
                "chunk_type": metadata.get("chunk_type"),
                "title": metadata.get("title"),
                "section": metadata.get("section"),
                "text": text[:800],
            }

            item_len = len(json.dumps(item, ensure_ascii=False))
            if total + item_len > max_chars_per_group:
                break

            total += item_len
            items.append(item)

        compact[key] = items

    return compact
