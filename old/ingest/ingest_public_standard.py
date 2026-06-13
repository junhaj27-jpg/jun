import os
import re
import uuid
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd
from tqdm import tqdm
from dotenv import load_dotenv
from qdrant_client.models import PointStruct

from rag.qdrant_config import get_client, get_embedder, ensure_collection, COLLECTION_NAME

load_dotenv()

XLSX_PATH = os.getenv(
    "PUBLIC_STANDARD_XLSX_PATH",
    "./data/terminology/공공데이터 공통표준(2025.11월).xlsx",
)


def normalize_text(text):
    text = str(text).replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def build_payload(
    *,
    text: str,
    chunk_id: str,
    doc_type: str,
    domain: str,
    source_name: str,
    section: str,
    title: str,
    applies_to: str,
    priority: str,
    source_file: str = "",
    version: str = "",
    chunk_type: str = "",
    keywords: List[str] | None = None,
    effective_date: str = "",
    is_active: bool = True,
    language: str = "ko",
    page: int | None = None,
):
    return {
        "text": text,
        "chunk_id": chunk_id,
        "doc_type": doc_type,
        "domain": domain,
        "source_name": source_name,
        "section": section,
        "title": title,
        "applies_to": applies_to,
        "priority": priority,
        "source_file": source_file,
        "version": version,
        "chunk_type": chunk_type,
        "keywords": keywords or [],
        "effective_date": effective_date,
        "is_active": is_active,
        "language": language,
        "page": page,
    }


def infer_public_standard_type(sheet_name: str):
    if "용어" in sheet_name:
        return "standard_term", "erd,database_design,table_design,column_design,column_name,table_name", "term_standard"
    if "단어" in sheet_name:
        return "standard_word", "erd,database_design,table_design,column_design,column_name,naming_rule", "word_standard"
    if "도메인" in sheet_name:
        return "standard_domain", "erd,database_design,table_design,column_design,data_type,column_type", "domain_standard"
    return "public_data_standard", "erd,database_design", "standard"


def ingest_common_standard_xlsx(xlsx_path):
    payloads = []
    xls = pd.ExcelFile(xlsx_path)

    print(f"[시트 목록] {xls.sheet_names}")

    for sheet_name in xls.sheet_names:
        df = pd.read_excel(xlsx_path, sheet_name=sheet_name).fillna("")
        doc_type, applies_to, chunk_type = infer_public_standard_type(sheet_name)

        for idx, row in df.iterrows():
            row_dict = row.to_dict()
            text_parts = []
            keywords = [sheet_name]

            for col, value in row_dict.items():
                value = normalize_text(value)
                if value:
                    text_parts.append(f"{col}: {value}")
                    if len(value) <= 50:
                        keywords.append(value)

            text = " | ".join(text_parts)
            if not text:
                continue

            chunk_id = f"public_standard_{sheet_name}_{idx + 1}"

            payloads.append(
                build_payload(
                    text=text,
                    chunk_id=chunk_id,
                    doc_type=doc_type,
                    domain="public_data",
                    source_name="공공데이터 공통표준",
                    section=sheet_name,
                    title=f"{sheet_name}_{idx + 1}",
                    applies_to=applies_to,
                    priority="required",
                    source_file=Path(xlsx_path).name,
                    version="2025.11",
                    chunk_type=chunk_type,
                    keywords=list(set(keywords))[:20],
                    effective_date="2025-11",
                )
            )

    return payloads


def upsert_payloads(payloads: List[Dict[str, Any]], batch_size: int = 32):
    client = get_client()
    embedder = get_embedder()

    for i in tqdm(range(0, len(payloads), batch_size)):
        batch = payloads[i:i + batch_size]
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

    print(f"[적재 완료] {len(payloads)}개")


def main():
    ensure_collection(recreate=False)
    payloads = ingest_common_standard_xlsx(XLSX_PATH)
    print(f"[추출 완료] 공공표준 chunk 수: {len(payloads)}")
    upsert_payloads(payloads)


if __name__ == "__main__":
    main()
