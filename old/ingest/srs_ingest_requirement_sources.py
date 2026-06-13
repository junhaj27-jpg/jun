import glob
import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List

from dotenv import load_dotenv
from qdrant_client.models import PointStruct
from tqdm import tqdm

from rag.qdrant_config import (
    REQUIREMENT_SOURCES_COLLECTION,
    ensure_named_collection,
    get_client,
    get_embedder,
)

load_dotenv()

COLLECTION_NAME = REQUIREMENT_SOURCES_COLLECTION
DATA_PIPELINE_ROOT = Path(os.getenv("REQUIREMENT_SOURCES_ROOT", "./data/requirement_sources"))


def iter_json_files() -> Iterable[Path]:
    patterns = [
        str(DATA_PIPELINE_ROOT / "*_final.json"),
        str(DATA_PIPELINE_ROOT / "RFP" / "*_requirements.json"),
    ]
    for pattern in patterns:
        for file_name in sorted(glob.glob(pattern)):
            yield Path(file_name)


def load_requirements(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("requirements"), list):
        return data["requirements"]
    if isinstance(data, list):
        return data
    return []


def requirement_text(req: Dict[str, Any]) -> str:
    parts = [
        req.get("requirement_id", ""),
        req.get("requirement_name", ""),
        req.get("requirement_type", ""),
        req.get("description", ""),
        " ".join(req.get("constraints") or []),
        " ".join(req.get("validation_criteria") or []),
        str(req.get("note") or ""),
    ]
    return " | ".join(str(p).strip() for p in parts if str(p).strip())


def build_payload(path: Path, req: Dict[str, Any], idx: int) -> Dict[str, Any]:
    text = requirement_text(req)
    req_id = str(req.get("requirement_id") or f"ROW-{idx}")
    chunk_id = f"requirement_source_{uuid.uuid5(uuid.NAMESPACE_DNS, f'{path.name}:{req_id}:{idx}')}"
    return {
        "text": text,
        "chunk_id": chunk_id,
        "doc_type": "rfp_requirement",
        "domain": "requirements",
        "source_name": path.stem,
        "section": "RFP extracted requirements",
        "title": req.get("requirement_name") or req_id,
        "requirement_id": req.get("requirement_id"),
        "requirement_name": req.get("requirement_name"),
        "requirement_type": req.get("requirement_type"),
        "source": req.get("source") or [],
        "applies_to": "requirements_definition,scope_analysis",
        "priority": req.get("priority") or "reference",
        "source_file": path.name,
        "chunk_type": "requirement_source",
        "keywords": ["RFP", "요구사항", str(req.get("requirement_type") or "")],
        "is_active": True,
        "language": "ko",
    }


def extract_payloads() -> List[Dict[str, Any]]:
    payloads = []
    for path in iter_json_files():
        requirements = load_requirements(path)
        print(f"[처리] {path.name}: {len(requirements)} requirements")
        for idx, req in enumerate(requirements, start=1):
            text = requirement_text(req)
            if text:
                payloads.append(build_payload(path, req, idx))
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

    print(f"[적재 완료] collection={COLLECTION_NAME}, requirements={len(payloads)}")


def main():
    ensure_named_collection(COLLECTION_NAME, recreate=False)
    payloads = extract_payloads()
    print(f"[추출 완료] requirement source rows={len(payloads)}")
    upsert_payloads(payloads)


if __name__ == "__main__":
    main()
