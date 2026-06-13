from rag.qdrant_config import (
    COLLECTION_NAME as ARKIVE_COLLECTION,
    REQUIREMENT_EXAMPLES_COLLECTION,
    REQUIREMENT_REFERENCE_COLLECTION,
    REQUIREMENT_SOURCES_COLLECTION,
    get_client,
)


def main():
    qdrant = get_client()
    collections = [
        ARKIVE_COLLECTION,
        REQUIREMENT_REFERENCE_COLLECTION,
        REQUIREMENT_SOURCES_COLLECTION,
        REQUIREMENT_EXAMPLES_COLLECTION,
    ]
    existing = {c.name for c in qdrant.get_collections().collections}

    for collection in collections:
        if collection not in existing:
            print(f"[없음] collection={collection}")
            continue
        count = qdrant.count(collection_name=collection).count
        print(f"[확인] collection={collection}, count={count}")


if __name__ == "__main__":
    main()

