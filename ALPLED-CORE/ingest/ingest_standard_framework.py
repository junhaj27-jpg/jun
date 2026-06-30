"""
[INGEST] 전자정부 표준프레임워크 적용가이드 v5.0

청킹 전략: □ 섹션 단위 분할 (초과 시 슬라이딩 윈도우 보조 분할)
패턴: r"□\s*.{2,20}"
페이지 필터: page < 47 (붙임 파트 제외)
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
        "STANDARD_FRAMEWORK_PATH",
        "./data/requirement_reference/기술/[가이드]표준프레임워크_적용가이드_v5.0.pdf",
    )
)

CHUNK_PATTERN = r"□\s*.{2,20}"
PAGE_FILTER = lambda page_num: page_num < 47  # 붙임 파트 제외

MAX_CHARS = 1500
OVERLAP = 150

DOC_TYPE = "technical_guide"
DOMAIN = "requirements"
APPLIES_TO = "requirements_definition,constraint_reference,architecture_design"
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
        title = extract_section_title(primary_chunk)

        sub_chunks = split_oversized_chunk(primary_chunk, max_chars=MAX_CHARS, overlap=OVERLAP)

        for sub_chunk in sub_chunks:
            chunk_index += 1
            page_num, search_pos = locate_chunk_page(sub_chunk, full_text, search_pos, page_offsets)

            chunk_id = make_chunk_id("standard_framework", SOURCE_PATH.name, str(chunk_index))
            payloads.append(
                build_base_payload(
                    text=sub_chunk,
                    chunk_id=chunk_id,
                    doc_type=DOC_TYPE,
                    domain=DOMAIN,
                    source_file=SOURCE_PATH,
                    section="기술",
                    title=title,
                    applies_to=APPLIES_TO,
                    priority=PRIORITY,
                    chunk_type="constraint_reference",
                    keywords=["전자정부", "표준프레임워크", "제약사항", "아키텍처"],
                    page=page_num,
                )
            )
    return payloads


def extract_section_title(chunk: str) -> str:
    """청크 시작 부분에서 '□ 섹션명' 형태를 추출.

    normalize_text()로 줄바꿈이 제거된 텍스트에서는 '□ 제목' 뒤에 \\n이나
    문자열 끝이 거의 나오지 않으므로, 다음 항목 마커 '○' 앞까지도 종료
    조건으로 인정한다 (예: '□ ...오픈소스SW 활용내역 (2.7기준) ○ 실행환경...'
    -> '...활용내역 (2.7기준)').
    """
    match = re.match(r"□\s*(.{2,40}?)(?:\s*○|\n|$)", chunk)
    return match.group(1).strip() if match else ""


def main():
    payloads = extract_payloads()
    print(f"[EXTRACTED] standard framework chunks={len(payloads)}")
    ensure_named_collection(TARGET_COLLECTION, recreate=False)
    upsert_payloads(payloads, TARGET_COLLECTION)


if __name__ == "__main__":
    main()