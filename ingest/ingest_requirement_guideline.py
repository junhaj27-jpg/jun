"""
[INGEST] 공공 SW사업 제안요청서 작성을 위한 요구사항 가이드 (2021.02.19)

청킹 전략: CHAPTER 단위 분할 (초과 시 슬라이딩 윈도우 보조 분할)
패턴: r"\d+\s*\nCHAPTER"
페이지 필터: page < 466 (붙임 제외, Part I~III 포함)

[평가 시 확인 필요]
- max_chars=2500, overlap=200 값이 적절한지 검토 필요
  (Chapter당 길이가 길어서 기본값(1500)보다 늘린 값. 평가 단계에서 비교 검토)
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
    normalize_text,
    upsert_payloads,
)
from rag.pdf_reader import read_pdf_pages
from rag.qdrant_config import ALPLED_REFERENCE_COLLECTION, ensure_named_collection

COLLECTION_NAME = ALPLED_REFERENCE_COLLECTION
SOURCE_PATH = Path(
    os.getenv(
        "REQUIREMENT_GUIDELINE_PATH",
        "./data/requirement_reference/요구사항 가이드/2.+공공+SW사업+제안요청서+작성을+위한+요구사항+가이드-20210219.pdf",
    )
)

CHUNK_PATTERN = r"\d+\s*\nCHAPTER"
PAGE_FILTER = lambda page_num: page_num < 466  # 붙임 1, 2 제외

# [평가 대상] Chapter당 길이가 길어 기본값(1500/150)보다 늘림. 추후 비교 필요.
MAX_CHARS = 2500
OVERLAP = 200

DOC_TYPE = "requirement_writing_guide"
DOMAIN = "requirements"
APPLIES_TO = "requirements_definition,acceptance_criteria_reference"
PRIORITY = "reference"


def extract_payloads() -> list[dict]:
    if not SOURCE_PATH.exists():
        print(f"[SKIP] file not found: {SOURCE_PATH}")
        return []

    # min_line_chars=1: 챕터 번호("01" 등 2자리 숫자 단독 줄)가 페이지번호/머리글
    #   노이즈로 오인되어 제거되지 않도록 함 (기본값 3에서는 제거됨).
    # normalize=False: CHUNK_PATTERN(r"\d+\s*\nCHAPTER")과 extract_chapter_info()의
    #   title 추출이 페이지 내부 줄바꿈에 의존하므로 보존. 서브 청크 저장 시점에
    #   normalize_text()를 별도로 적용함.
    full_text, page_offsets = merge_pages_with_offsets(
        read_pdf_pages(SOURCE_PATH, page_filter=PAGE_FILTER, min_line_chars=1),
        normalize=False,
    )

    # 1. Chapter 단위로 1차 분할
    primary_chunks = split_by_pattern(full_text, CHUNK_PATTERN)

    payloads = []
    search_pos = 0
    chunk_index = 0

    for primary_chunk in primary_chunks:
        # Chapter 정보는 1차 청크에서 한 번만 추출
        chapter_no, title = extract_chapter_info(primary_chunk)
        section = f"Chapter {chapter_no}" if chapter_no else "요구사항 가이드"

        # 2. 길이 초과 시 슬라이딩 윈도우로 추가 분할 (title/section은 동일하게 전파)
        sub_chunks = split_oversized_chunk(primary_chunk, max_chars=MAX_CHARS, overlap=OVERLAP)

        for sub_chunk in sub_chunks:
            chunk_index += 1
            page_num, search_pos = locate_chunk_page(sub_chunk, full_text, search_pos, page_offsets)

            chunk_id = make_chunk_id("requirement_guideline", SOURCE_PATH.name, str(chunk_index))
            payloads.append(
                build_base_payload(
                    text=normalize_text(sub_chunk),
                    chunk_id=chunk_id,
                    doc_type=DOC_TYPE,
                    domain=DOMAIN,
                    source_file=SOURCE_PATH,
                    section=section,
                    title=title,
                    applies_to=APPLIES_TO,
                    priority=PRIORITY,
                    chunk_type="acceptance_criteria_reference",
                    keywords=["요구사항", "공공SW", "제안요청서", "검수기준"],
                    page=page_num,
                )
            )
    return payloads


def extract_chapter_info(chunk: str) -> tuple[str, str]:
    """청크 시작 부분에서 'NN\nCHAPTER \n• 제목' 형태를 추출."""
    chapter_no = ""
    title = ""

    no_match = re.match(r"(\d+)\s*\nCHAPTER", chunk)
    if no_match:
        chapter_no = no_match.group(1)

    title_match = re.search(r"CHAPTER\s*\n*\s*•\s*([^\n]+)", chunk)
    if title_match:
        title = title_match.group(1).strip()

    return chapter_no, title


def main():
    ensure_named_collection(COLLECTION_NAME, recreate=False)
    payloads = extract_payloads()
    print(f"[EXTRACTED] requirement guideline chunks={len(payloads)}")
    upsert_payloads(payloads, COLLECTION_NAME)


if __name__ == "__main__":
    main()