from qdrant_client.models import FieldCondition, Filter, MatchValue

from rag.qdrant_config import (
    REQUIREMENT_EXAMPLES_COLLECTION,
    REQUIREMENT_REFERENCE_COLLECTION,
    REQUIREMENT_SOURCES_COLLECTION,
    get_client,
    get_embedding,
)


def search_knowledge(
    query_text: str,
    *,
    collection_name: str | None = None,
    doc_type_filter: str | None = None,
    top_k: int = 5,
):
    qdrant = get_client()
    vector = get_embedding(query_text)
    collections = [
        collection_name,
    ] if collection_name else [
        REQUIREMENT_REFERENCE_COLLECTION,
        REQUIREMENT_SOURCES_COLLECTION,
        REQUIREMENT_EXAMPLES_COLLECTION,
    ]

    query_filter = None
    if doc_type_filter:
        query_filter = Filter(
            must=[
                FieldCondition(
                    key="doc_type",
                    match=MatchValue(value=doc_type_filter),
                )
            ]
        )

    results = []
    existing = {c.name for c in qdrant.get_collections().collections}
    for collection in collections:
        if collection not in existing:
            continue
        results.extend(
            qdrant.query_points(
                collection_name=collection,
                query=vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            ).points
        )

    rows = sorted(results, key=lambda p: p.score or 0, reverse=True)[:top_k]
    return [
        {
            "score": row.score,
            "text": (row.payload or {}).get("text", ""),
            "metadata": row.payload or {},
        }
        for row in rows
    ]


def search_requirement_reference(query_text: str, doc_type_filter: str = None, top_k: int = 5):
    return search_knowledge(
        query_text,
        collection_name=REQUIREMENT_REFERENCE_COLLECTION,
        doc_type_filter=doc_type_filter,
        top_k=top_k,
    )


def search_requirement_sources(query_text: str, top_k: int = 5):
    return search_knowledge(
        query_text,
        collection_name=REQUIREMENT_SOURCES_COLLECTION,
        top_k=top_k,
    )


def search_requirement_examples(query_text: str, top_k: int = 5):
    return search_knowledge(
        query_text,
        collection_name=REQUIREMENT_EXAMPLES_COLLECTION,
        top_k=top_k,
    )
