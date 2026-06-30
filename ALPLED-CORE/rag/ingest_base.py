import re
import uuid
from pathlib import Path
from typing import Any, Iterable


def normalize_text(value: Any) -> str:
    text = str(value if value is not None else "").replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def make_chunk_id(prefix: str, *parts: str) -> str:
    """청크 고유 ID 생성 (uuid5 기반, 재현 가능)."""
    base = ":".join(str(p) for p in parts)
    return f"{prefix}_{uuid.uuid5(uuid.NAMESPACE_DNS, base)}"


def merge_pages_with_offsets(
    pages: Iterable[tuple[int, str]],
    *,
    normalize: bool = True,
) -> tuple[str, list[tuple[int, int]]]:
    """
    (페이지번호, 텍스트) 이터러블을 받아 전체 텍스트와 페이지 offset 목록을 반환.

    normalize=True(기본값)면 각 페이지 텍스트에 normalize_text()를 적용해
    줄바꿈을 공백으로 치환한다 (기존 동작과 동일).
    normalize=False면 원본 줄바꿈을 보존한다 (페이지 내부 줄바꿈에 의존하는
    패턴 매칭/타이틀 추출이 필요한 경우 사용. 이 경우 split_oversized_chunk
    이후 저장 직전에 normalize_text()를 별도로 적용해야 함).

    page_offsets: [(offset, page_num), ...] - offset은 full_text 내 시작 위치
    """
    full_text = ""
    page_offsets = []
    for page_num, page_text in pages:
        text = normalize_text(page_text) if normalize else page_text
        page_offsets.append((len(full_text), page_num))
        full_text += text + "\n"
    return full_text, page_offsets


def resolve_page(pos: int, page_offsets: list[tuple[int, int]]) -> int:
    """텍스트 offset에 해당하는 시작 페이지 번호를 찾음."""
    page_num = page_offsets[0][1]
    for offset, num in page_offsets:
        if offset <= pos:
            page_num = num
        else:
            break
    return page_num


def locate_chunk_page(
    chunk: str,
    full_text: str,
    search_pos: int,
    page_offsets: list[tuple[int, int]],
) -> tuple[int, int]:
    """
    청크의 시작 페이지 번호와 다음 검색 시작 위치를 반환.

    Returns:
        (page_num, next_search_pos)
    """
    chunk_pos = full_text.find(chunk, search_pos)
    if chunk_pos == -1:
        chunk_pos = search_pos
    next_search_pos = chunk_pos + len(chunk)
    page_num = resolve_page(chunk_pos, page_offsets)
    return page_num, next_search_pos


def build_base_payload(
    *,
    text: str,
    chunk_id: str,
    doc_type: str,
    domain: str,
    source_file: Path,
    section: str = "",
    title: str = "",
    applies_to: str = "",
    priority: str = "reference",
    version: str = "",
    chunk_type: str = "",
    keywords: list[str] | None = None,
    is_active: bool = True,
    language: str = "ko",
    page: int | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    모든 ingest 스크립트가 공통으로 쓰는 payload 기본 구조.
    파일별로 필요한 추가 필드는 extra로 병합.
    """
    payload = {
        "text": text,
        "chunk_id": chunk_id,
        "doc_type": doc_type,
        "domain": domain,
        "source_name": source_file.stem,
        "section": section,
        "title": title or section,
        "applies_to": applies_to,
        "priority": priority,
        "source_file": source_file.name,
        "version": version,
        "chunk_type": chunk_type,
        "keywords": keywords or [],
        "is_active": is_active,
        "language": language,
        "page": page,
    }
    if extra:
        payload.update(extra)
    return payload


def upsert_payloads(
    payloads: list[dict[str, Any]],
    collection_name: str,
    *,
    batch_size: int = 32,
) -> None:
    from qdrant_client.models import PointStruct

    from rag.qdrant_config import get_client, get_embedder

    try:
        from tqdm import tqdm
    except ModuleNotFoundError:
        tqdm = lambda value: value  # noqa: E731

    if not payloads:
        print(f"[SKIP] no payloads for collection={collection_name}")
        return

    client = get_client()
    embedder = get_embedder()

    for start in tqdm(range(0, len(payloads), batch_size)):
        batch = payloads[start : start + batch_size]
        vectors = embedder.encode(
            [payload["text"] for payload in batch],
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()
        points = [
            PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_DNS, payload["chunk_id"])),
                vector=vector,
                payload=payload,
            )
            for vector, payload in zip(vectors, batch)
        ]
        client.upsert(collection_name=collection_name, points=points)

    print(f"[DONE] collection={collection_name}, chunks={len(payloads)}")
    