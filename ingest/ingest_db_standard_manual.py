"""
[INGEST] 공공데이터베이스 표준화 관리 매뉴얼 (2023.4)

청킹 전략: 소절(N.N 또는 N.N.N) 단위 분할 (초과 시 슬라이딩 윈도우 보조 분할)
패턴: r"\d+\.\d+(?:\.\d+)?\s+\S"
페이지 필터: 11 <= page < 174 (I~IV장만, V장 메타데이터 관리시스템 제외)

[참고] 패턴이 본문 소절 번호 외에 표/추진과제 번호(예: p.40 진단항목 1.1~4.2,
p.36 "추진과제 2.1")에도 매칭되는 경우가 있음. 다만 해당 조각들도 의미 있는
내용(진단기준 등)을 포함하고 있어 retrieval 가치는 유지됨. title이 정확한
소절명이 아닐 수 있다는 점만 평가 시 참고.

[참고] erd_rag_service.py에서 doc_type="db_standard_manual"로 쿼리하는
DB_ERD_REFERENCE_COLLECTION에 적재됨. 공공데이터 공통표준.xlsx
(ingest_public_standard.py)도 동일 collection 사용.
"""

import os
import re
from pathlib import Path

from rag.chunker import split_by_pattern, split_oversized_chunk
from rag.ingest_base import (
    build_base_payload,
    locate_chunk_page,
    make_chunk_id,
    merge_pages_with_offsets,
    upsert_payloads,
)
from rag.pdf_reader import read_pdf_pages
from rag.qdrant_config import ALPLED_REFERENCE_COLLECTION, ensure_named_collection

TARGET_COLLECTION = ALPLED_REFERENCE_COLLECTION

SOURCE_PATH = Path(
    os.getenv(
        "DB_STANDARD_MANUAL_PATH",
        "./data/requirement_reference/요구사항 가이드/공공데이터베이스_표준화_관리_매뉴얼_23년_4월.pdf",
    )
)

CHUNK_PATTERN = r"\d+\.\d+(?:\.\d+)?\s+\S"
PAGE_FILTER = lambda page_num: 11 <= page_num < 174  # I~IV장만 (V장 메타데이터 관리시스템 제외)

MAX_CHARS = 1500
OVERLAP = 150

DOC_TYPE = "db_standard_manual"
DOMAIN = "public_data"
APPLIES_TO = "erd,database_design,table_design,column_design,column_name,naming_rule"
PRIORITY = "required"


def extract_payloads() -> list[dict]:
    if not SOURCE_PATH.exists():
        print(f"[SKIP] file not found: {SOURCE_PATH}")
        return []

    full_text, page_offsets = merge_pages_with_offsets(
        read_pdf_pages(SOURCE_PATH, page_filter=PAGE_FILTER)
    )

    primary_chunks = split_by_pattern(full_text, CHUNK_PATTERN)

    payloads = []
    search_pos = 0
    chunk_index = 0

    for primary_chunk in primary_chunks:
        section_no, title = extract_section_info(primary_chunk)

        sub_chunks = split_oversized_chunk(primary_chunk, max_chars=MAX_CHARS, overlap=OVERLAP)

        for sub_chunk in sub_chunks:
            chunk_index += 1
            page_num, search_pos = locate_chunk_page(sub_chunk, full_text, search_pos, page_offsets)

            chunk_id = make_chunk_id("db_standard_manual", SOURCE_PATH.name, str(chunk_index))
            payloads.append(
                build_base_payload(
                    text=sub_chunk,
                    chunk_id=chunk_id,
                    doc_type=DOC_TYPE,
                    domain=DOMAIN,
                    source_file=SOURCE_PATH,
                    section=section_no or "공공데이터베이스 표준화 관리 매뉴얼",
                    title=title,
                    applies_to=APPLIES_TO,
                    priority=PRIORITY,
                    chunk_type="db_standard_reference",
                    keywords=["공공데이터베이스", "표준화", "DB설계", "ERD"],
                    page=page_num,
                )
            )
    return payloads


def extract_section_info(chunk: str) -> tuple[str, str]:
    """청크 시작 부분에서 '1.1 표준화 관리체계' 형태에서 소절 번호와 제목을 추출."""
    match = re.match(r"(\d+\.\d+(?:\.\d+)?)\s+(\S[^\n]{0,40})", chunk)
    if match:
        return match.group(1), match.group(2).strip()
    return "", ""


def main():
    ensure_named_collection(TARGET_COLLECTION, recreate=False)
    payloads = extract_payloads()
    print(f"[EXTRACTED] db standard manual chunks={len(payloads)}")
    upsert_payloads(payloads, TARGET_COLLECTION)


if __name__ == "__main__":
    main()