import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List

from dotenv import load_dotenv
from qdrant_client.models import PointStruct
from tqdm import tqdm

from rag.qdrant_config import (
    REQUIREMENT_EXAMPLES_COLLECTION,
    ensure_named_collection,
    get_client,
    get_embedder,
)

load_dotenv()

COLLECTION_NAME = REQUIREMENT_EXAMPLES_COLLECTION
EXAMPLES_ROOT = Path(
    os.getenv("REQUIREMENT_EXAMPLES_ROOT", "./data/requirement_examples/GDS")
)


def iter_json_files() -> Iterable[Path]:
    if not EXAMPLES_ROOT.exists():
        print(f"[스킵] 폴더 없음: {EXAMPLES_ROOT}")
        return
    for path in sorted(EXAMPLES_ROOT.glob("*.json")):
        yield path


def flatten_example_items(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get("requirements"), list):
        return data["requirements"]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def example_text(item: Dict[str, Any]) -> str:
    parts = []
    for key, value in item.items():
        if isinstance(value, list):
            value = " ".join(str(v) for v in value)
        elif isinstance(value, dict):
            value = json.dumps(value, ensure_ascii=False)
        if value:
            parts.append(f"{key}: {value}")
    return " | ".join(parts)


def build_payload(path: Path, item: Dict[str, Any], idx: int) -> Dict[str, Any]:
    text = example_text(item)
    name = item.get("requirement_name") or item.get("name") or f"example_{idx}"
    chunk_id = f"requirement_example_{uuid.uuid5(uuid.NAMESPACE_DNS, f'{path.name}:{idx}:{text[:120]}')}"
    return {
        "text": text,
        "chunk_id": chunk_id,
        "doc_type": "requirement_example",
        "domain": "requirements",
        "source_name": path.stem,
        "section": "GDS",
        "title": name,
        "applies_to": "requirements_definition,validation_criteria,writing_pattern",
        "priority": "reference",
        "source_file": path.name,
        "chunk_type": "requirement_example",
        "keywords": ["요구사항", "예시", "GDS"],
        "is_active": True,
        "language": "ko",
    }


def extract_payloads() -> List[Dict[str, Any]]:
    payloads = []
    for path in iter_json_files():
        data = json.loads(path.read_text(encoding="utf-8"))
        items = flatten_example_items(data)
        print(f"[처리] {path.name}: {len(items)} examples")
        for idx, item in enumerate(items, start=1):
            text = example_text(item)
            if text:
                payloads.append(build_payload(path, item, idx))
    return payloads


def upsert_payloads(payloads: List[Dict[str, Any]], batch_size: int = 64):
    client = get_client()
    embedder = get_embedder()

    for i in tqdm(range(0, len(payloads), batch_size)):
        batch = payloads[i : i + batch_size]
        vectors = embedder.encode(
            [p["text"] for p in batch],
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
        client.upsert(collection_name=COLLECTION_NAME, points=points)

    print(f"[적재 완료] collection={COLLECTION_NAME}, examples={len(payloads)}")


def main():
    ensure_named_collection(COLLECTION_NAME, recreate=False)
    payloads = extract_payloads()
    print(f"[추출 완료] requirement examples={len(payloads)}")
    upsert_payloads(payloads)


if __name__ == "__main__":
    main()
