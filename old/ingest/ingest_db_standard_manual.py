import os
import re
import uuid
from pathlib import Path
from typing import List, Dict, Any

import fitz
from tqdm import tqdm
from dotenv import load_dotenv
from qdrant_client.models import PointStruct

from rag.qdrant_config import get_client, get_embedder, ensure_collection, COLLECTION_NAME

load_dotenv()

PDF_PATH = os.getenv(
    "DB_STANDARD_MANUAL_PATH",
    "./data/db_standards/공공데이터베이스_표준화_관리_매뉴얼_202106.pdf",
)


def normalize_text(text: str) -> str:
    text = str(text).replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_text_by_size(text: str, chunk_size: int = 900, overlap: int = 120) -> List[str]:
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()

        if len(chunk) >= 100:
            chunks.append(chunk)

        start = end - overlap

    return chunks


def infer_section(page_num: int) -> str:
    if 1 <= page_num <= 14:
        return "공공데이터베이스 표준화 총론"
    if 15 <= page_num <= 28:
        return "공공데이터베이스 표준화 추진체계"
    if 29 <= page_num <= 60:
        return "공공데이터 구축 시 표준화 관리"
    if 61 <= page_num <= 128:
        return "공공데이터베이스 공통표준용어 관리"
    if 129 <= page_num <= 168:
        return "공공데이터베이스 메타데이터 관리"
    if 169 <= page_num <= 208:
        return "공공데이터베이스 표준화 관련서식"
    if page_num >= 209:
        return "공공기관의 데이터베이스 표준화 지침"
    return "기타"


def infer_chunk_type(section: str, text: str) -> str:
    if "서식" in section:
        return "template_form"
    if "메타데이터" in section:
        return "metadata_policy"
    if "공통표준용어" in section:
        return "standard_term_rule"
    if "공통표준단어" in text:
        return "standard_word_rule"
    if "공통표준도메인" in text:
        return "standard_domain_rule"
    if "표준코드" in text:
        return "standard_code_rule"
    if "데이터타입" in text or "데이터길이" in text:
        return "data_type_rule"
    if "테이블정의서" in text or "컬럼정의서" in text or "데이터베이스정의서" in text:
        return "db_design_form"
    return "standard_guide"


def build_payload(
    *,
    text: str,
    chunk_id: str,
    page: int,
    chunk_idx: int,
    section: str,
    chunk_type: str,
) -> Dict[str, Any]:
    return {
        "text": text,
        "chunk_id": chunk_id,
        "doc_type": "db_standard_manual",
        "domain": "public_data",
        "source_name": "공공데이터베이스 표준화 관리 매뉴얼",
        "section": section,
        "title": f"{section} p.{page}-{chunk_idx}",
        "applies_to": "database_design,table_design,column_design,erd,metadata,standardization",
        "priority": "required",
        "source_file": Path(PDF_PATH).name,
        "version": "2021.06",
        "chunk_type": chunk_type,
        "keywords": [
            "공공데이터베이스",
            "표준화",
            "공통표준용어",
            "공통표준단어",
            "공통표준도메인",
            "메타데이터",
            "데이터베이스정의서",
            "테이블정의서",
            "컬럼정의서",
        ],
        "effective_date": "2021-06",
        "is_active": True,
        "language": "ko",
        "page": page,
    }


def extract_manual_chunks(pdf_path: str) -> List[Dict[str, Any]]:
    doc = fitz.open(pdf_path)
    payloads = []

    for page_idx in range(len(doc)):
        page_num = page_idx + 1
        text = normalize_text(doc[page_idx].get_text())

        if not text or len(text) < 80:
            continue

        section = infer_section(page_num)
        chunks = split_text_by_size(text, chunk_size=900, overlap=120)

        for chunk_idx, chunk in enumerate(chunks, start=1):
            chunk_type = infer_chunk_type(section, chunk)
            chunk_id = f"db_standard_manual_p{page_num}_c{chunk_idx}"

            payloads.append(
                build_payload(
                    text=chunk,
                    chunk_id=chunk_id,
                    page=page_num,
                    chunk_idx=chunk_idx,
                    section=section,
                    chunk_type=chunk_type,
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

    print(f"[적재 완료] {len(payloads)} chunks")


def main():
    ensure_collection(recreate=False)
    payloads = extract_manual_chunks(PDF_PATH)
    print(f"[추출 완료] DB 표준화 매뉴얼 chunk 수: {len(payloads)}")
    upsert_payloads(payloads)


if __name__ == "__main__":
    main()
