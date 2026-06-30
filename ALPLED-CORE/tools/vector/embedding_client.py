"""검색 질의 임베딩 벡터를 생성합니다."""

from functools import lru_cache
from typing import Any

from config.settings import Settings, get_settings
from tools.result import ToolResult, error_result, success_result


def embed_text(
    text: str,
    *,
    model_name: str | None = None,
    embedder: Any | None = None,
    settings: Settings | None = None,
) -> ToolResult:
    """SentenceTransformer 기반으로 Qdrant 검색용 query vector를 생성합니다."""

    if not text.strip():
        return error_result("EMBEDDING_EMPTY_TEXT", "임베딩할 텍스트가 비어 있습니다.")

    settings = settings or get_settings()
    selected_model = model_name or settings.embed_model_name
    try:
        model = embedder or _get_embedder(selected_model)
        vector = model.encode(text, normalize_embeddings=True)
        if hasattr(vector, "tolist"):
            vector = vector.tolist()
        return success_result({"embedding": list(vector), "model_name": selected_model})
    except ImportError as exc:
        return error_result("EMBEDDING_CLIENT_UNAVAILABLE", str(exc))
    except Exception as exc:
        return error_result("EMBEDDING_FAILED", str(exc))


@lru_cache
def _get_embedder(model_name: str) -> Any:
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)
