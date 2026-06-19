import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL") or (
    f"http://{os.getenv('QDRANT_HOST', 'localhost')}:{os.getenv('QDRANT_PORT', '6333')}"
)
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
EMBED_MODEL_NAME = (
    os.getenv("EMBED_MODEL_NAME")
    or os.getenv("EMBEDDING_MODEL")
    or "BAAI/bge-m3"
)

ALPLED_REFERENCE_COLLECTION = os.getenv(
    "ALPLED_REFERENCE_COLLECTION",
    "ALPLED_reference",
)
COLLECTION_NAME = ALPLED_REFERENCE_COLLECTION
REQUIREMENT_RAG_TOP_K = int(os.getenv("REQUIREMENT_RAG_TOP_K", "3"))

_client = None
_embedder = None


def get_client() -> Any:
    global _client
    if _client is None:
        from qdrant_client import QdrantClient

        kwargs = {"url": QDRANT_URL}
        if QDRANT_API_KEY:
            kwargs["api_key"] = QDRANT_API_KEY
        _client = QdrantClient(**kwargs)
    return _client


def get_embedder() -> Any:
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer

        _embedder = SentenceTransformer(EMBED_MODEL_NAME)
    return _embedder


def get_embedding(text: str):
    return get_embedder().encode(text, normalize_embeddings=True).tolist()


def get_embeddings(texts: list[str]):
    if not texts:
        return []
    return get_embedder().encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).tolist()


def ensure_named_collection(collection_name: str, recreate: bool = False):
    from qdrant_client.models import Distance, VectorParams

    client = get_client()
    embedder = get_embedder()
    dim = embedder.get_sentence_embedding_dimension()

    existing = [c.name for c in client.get_collections().collections]

    if recreate and collection_name in existing:
        client.delete_collection(collection_name=collection_name)
        existing.remove(collection_name)

    if collection_name not in existing:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        print(f"[생성 완료] collection={collection_name}, dim={dim}")
    else:
        print(f"[이미 존재] collection={collection_name}")


def ensure_collection(recreate: bool = False):
    ensure_named_collection(COLLECTION_NAME, recreate=recreate)

