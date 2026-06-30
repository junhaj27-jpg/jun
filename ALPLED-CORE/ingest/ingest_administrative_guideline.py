"""
[INGEST] 행정기관 및 공공기관 정보시스템 구축·운영 지침 (행정안전부고시 제2025-1호)

청킹 전략: 조(條) 단위 분할 (초과 시 슬라이딩 윈도우 보조 분할)
패턴: r"제\d+조"
페이지 필터: 없음 (전체 20페이지 처리)
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
from rag.qdrant_config import (
    ALPLED_REFERENCE_COLLECTION,
    ensure_named_collection,
)
TARGET_COLLECTION = ALPLED_REFERENCE_COLLECTION

SOURCE_PATH = Path(
    os.getenv(
        "ADMINISTRATIVE_GUIDELINE_PATH",
        "./data/requirement_reference/강제 규정/행정기관 및 공공기관 정보시스템 구축·운영 지침 (행정안전부고시)(제2025-1호)(20250102).pdf",
    )
)

CHUNK_PATTERN = r"제\d+조"
PAGE_FILTER = None  # 전체 페이지 처리

MAX_CHARS = 1500
OVERLAP = 150

DOC_TYPE = "compliance_rule"
DOMAIN = "requirements"
APPLIES_TO = "requirements_definition,constraint_reference"
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
        title = extract_article_title(primary_chunk)

        sub_chunks = split_oversized_chunk(primary_chunk, max_chars=MAX_CHARS, overlap=OVERLAP)

        for sub_chunk in sub_chunks:
            chunk_index += 1
            page_num, search_pos = locate_chunk_page(sub_chunk, full_text, search_pos, page_offsets)

            chunk_id = make_chunk_id("administrative_guideline", SOURCE_PATH.name, str(chunk_index))
            payloads.append(
                build_base_payload(
                    text=sub_chunk,
                    chunk_id=chunk_id,
                    doc_type=DOC_TYPE,
                    domain=DOMAIN,
                    source_file=SOURCE_PATH,
                    section="강제 규정",
                    title=title,
                    applies_to=APPLIES_TO,
                    priority=PRIORITY,
                    chunk_type="constraint_reference",
                    keywords=["행정기관", "공공기관", "정보시스템", "구축운영지침", "제약사항"],
                    page=page_num,
                )
            )
    return payloads


def extract_article_title(chunk: str) -> str:
    """청크 시작 부분에서 '제N조(제목)' 형태를 추출."""
    match = re.match(r"(제\d+조(?:의\d+)?)\s*\(([^)]+)\)", chunk)
    if match:
        return f"{match.group(1)}({match.group(2)})"
    match = re.match(r"제\d+조(?:의\d+)?", chunk)
    return match.group(0) if match else ""


def main():
    payloads = extract_payloads()
    print(f"[EXTRACTED] administrative guideline chunks={len(payloads)}")
    ensure_named_collection(TARGET_COLLECTION, recreate=False)
    upsert_payloads(payloads, TARGET_COLLECTION)


if __name__ == "__main__":
    main()