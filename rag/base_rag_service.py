import json
from typing import Any

from qdrant_client.models import FieldCondition, Filter, MatchValue

from rag.qdrant_config import COLLECTION_NAME, get_client, get_embedder


def search_rag(
    query: str,
    *,
    collection_name: str = COLLECTION_NAME,
    domain: str | None = None,
    applies_to: str | None = None,
    doc_type: str | None = None,
    chunk_type: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    client = get_client()
    embedder = get_embedder()
    query_vector = embedder.encode(query, normalize_embeddings=True).tolist()

    conditions = [FieldCondition(key="is_active", match=MatchValue(value=True))]
    if domain:
        conditions.append(FieldCondition(key="domain", match=MatchValue(value=domain)))
    if doc_type:
        conditions.append(FieldCondition(key="doc_type", match=MatchValue(value=doc_type)))
    if chunk_type:
        conditions.append(FieldCondition(key="chunk_type", match=MatchValue(value=chunk_type)))

    result = client.query_points(
        collection_name=collection_name,
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

        rows.append(
            {
                "score": item.score,
                "text": payload.get("text", ""),
                "metadata": payload,
            }
        )
        if len(rows) >= limit:
            break
    return rows


def compact_rag_context(rag_context: dict[str, Any], max_chars_per_group: int = 3500) -> dict[str, Any]:
    compact = {}

    for key, value in rag_context.items():
        if key == "domain":
            compact[key] = value
            continue
        if not isinstance(value, list):
            compact[key] = value
            continue

        items = []
        total = 0
        for row in value:
            if not isinstance(row, dict):
                continue
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
