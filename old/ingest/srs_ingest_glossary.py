import hashlib
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from dotenv import load_dotenv
from qdrant_client.models import PointStruct
from tqdm import tqdm

from rag.qdrant_config import get_client, get_embedder, ensure_named_collection

load_dotenv()

DEFAULT_XLSX_PATH = "./data/terminology/용어사전/2025+정보통신용어사전+수록+용어.xlsx"
XLSX_PATH = os.getenv("SRS_GLOSSARY_XLSX_PATH", DEFAULT_XLSX_PATH)
COLLECTION_NAME = os.getenv("SRS_GLOSSARY_COLLECTION", "arkive")


def normalize_text(value: Any) -> str:
    text = str(value if value is not None else "").replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def first_existing(row: Dict[str, Any], candidates: List[str]) -> str:
    normalized = {normalize_text(k).replace(" ", ""): v for k, v in row.items()}
    for candidate in candidates:
        value = normalized.get(candidate.replace(" ", ""))
        value = normalize_text(value)
        if value:
            return value
    return ""


def stable_chunk_id(sheet_name: str, row_index: int, text: str) -> str:
    digest = hashlib.sha1(f"{sheet_name}:{row_index}:{text}".encode("utf-8")).hexdigest()
    return f"glossary_{digest[:16]}"


def build_payload(
    *,
    text: str,
    chunk_id: str,
    sheet_name: str,
    row_index: int,
    row: Dict[str, Any],
    source_file: str,
) -> Dict[str, Any]:
    term = first_existing(
        row,
        ["용어", "용어명", "표준용어", "한글명", "국문명", "단어명", "term"],
    )
    definition = first_existing(
        row,
        ["정의", "설명", "용어설명", "의미", "definition", "description"],
    )
    english = first_existing(
        row,
        ["영문", "영문명", "영어", "영어명", "약어", "english", "abbr"],
    )

    keywords = [sheet_name, term, english]
    keywords.extend(
        normalize_text(value)
        for value in row.values()
        if 0 < len(normalize_text(value)) <= 40
    )

    return {
        "text": text,
        "chunk_id": chunk_id,
        "doc_type": "glossary_term",
        "domain": "terminology",
        "source_name": "정보통신용어사전",
        "section": sheet_name,
        "title": term or f"{sheet_name}_{row_index}",
        "term": term,
        "definition": definition,
        "english": english,
        "applies_to": "requirements_definition,terminology,glossary",
        "priority": "reference",
        "source_file": source_file,
        "version": "2025",
        "chunk_type": "glossary_term",
        "keywords": sorted({k for k in keywords if k})[:30],
        "effective_date": "2025",
        "is_active": True,
        "language": "ko",
        "row_index": row_index,
    }


def extract_glossary_payloads(xlsx_path: str) -> List[Dict[str, Any]]:
    payloads = []
    xls = pd.ExcelFile(xlsx_path)
    print(f"[시트 목록] {xls.sheet_names}")

    for sheet_name in xls.sheet_names:
        df = pd.read_excel(xlsx_path, sheet_name=sheet_name).fillna("")

        for idx, row in df.iterrows():
            row_dict = row.to_dict()
            text_parts = []

            for col, value in row_dict.items():
                value = normalize_text(value)
                if value:
                    text_parts.append(f"{normalize_text(col)}: {value}")

            text = " | ".join(text_parts)
            if not text:
                continue

            chunk_id = stable_chunk_id(sheet_name, idx + 1, text)
            payloads.append(
                build_payload(
                    text=text,
                    chunk_id=chunk_id,
                    sheet_name=sheet_name,
                    row_index=idx + 1,
                    row=row_dict,
                    source_file=Path(xlsx_path).name,
                )
            )

    return payloads


def upsert_payloads(payloads: List[Dict[str, Any]], batch_size: int = 64):
    client = get_client()
    embedder = get_embedder()

    for i in tqdm(range(0, len(payloads), batch_size)):
        batch = payloads[i : i + batch_size]
        texts = [p["text"] for p in batch]

        vectors = embedder.encode(
            texts,
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

    print(f"[적재 완료] collection={COLLECTION_NAME}, glossary rows={len(payloads)}")


def main():
    if not Path(XLSX_PATH).exists():
        raise FileNotFoundError(f"용어사전 파일을 찾을 수 없습니다: {XLSX_PATH}")

    ensure_named_collection(COLLECTION_NAME, recreate=False)
    payloads = extract_glossary_payloads(XLSX_PATH)
    print(f"[추출 완료] 용어사전 row 수: {len(payloads)}")
    upsert_payloads(payloads)


if __name__ == "__main__":
    main()
