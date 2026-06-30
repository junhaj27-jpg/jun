"""
[INGEST] 공공정보화사업 단계별 사업관리 가이드 (2023.2)

청킹 전략: 부록 단위 분할 (초과 시 슬라이딩 윈도우 보조 분할)
패턴: r"부록\s*\d{2}" (전체 부록을 경계로 인식 후, 필요한 부록만 필터링)
대상 부록: 03, 04, 08
페이지 필터: page >= 83 (부록 03 시작 이전 본문 제외)
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

COLLECTION_NAME = ALPLED_REFERENCE_COLLECTION
SOURCE_PATH = Path(
    os.getenv(
        "PROJECT_MANAGEMENT_GUIDE_PATH",
        "./data/requirement_reference/요구사항 가이드/공공정보화사업_단계별_사업관리가이드(2023.2).pdf",
    )
)

# 전체 부록을 경계로 분할 후, TARGET_APPENDIX만 추출 (부록05~07 등이 부록04에 섞이는 것 방지)
CHUNK_PATTERN = r"부록\s*\d{2}"
TARGET_APPENDIX = {"03", "04", "08"}
PAGE_FILTER = lambda page_num: page_num >= 83  # 부록 03 시작 이전 본문 제외

MAX_CHARS = 1500
OVERLAP = 150

DOC_TYPE = "project_management_guide"
DOMAIN = "requirements"
APPLIES_TO = "requirements_definition,constraint_reference,acceptance_criteria_reference"
PRIORITY = "reference"

# 부록별 doc_type/chunk_type 세분화
APPENDIX_META = {
    "03": {
        "title": "과업규모 산정을 위한 기능요구사항 작성가이드",
        "chunk_type": "acceptance_criteria_reference",
        "keywords": ["과업규모", "기능요구사항", "검수기준"],
    },
    "04": {
        "title": "상호운용성 등 기술평가표",
        "chunk_type": "acceptance_criteria_reference",
        "keywords": ["상호운용성", "기술평가", "검수기준"],
    },
    "08": {
        "title": "법규 상 기술 준수사항의 제안요청서 반영 사례",
        "chunk_type": "constraint_reference",
        "keywords": ["법규", "기술준수사항", "제약사항"],
    },
}


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
        appendix_no = extract_appendix_no(primary_chunk)

        if appendix_no not in TARGET_APPENDIX:
            # 대상 부록이 아니면 청크는 생성하지 않되, search_pos는 갱신해
            # 이후 청크의 페이지 위치 탐색이 정확하고 효율적으로 이뤄지게 한다.
            chunk_pos = full_text.find(primary_chunk, search_pos)
            if chunk_pos != -1:
                search_pos = chunk_pos + len(primary_chunk)
            continue

        meta = APPENDIX_META.get(appendix_no, {})
        title = meta.get("title", f"부록 {appendix_no}")
        chunk_type = meta.get("chunk_type", "reference")
        keywords = meta.get("keywords", ["사업관리"])

        sub_chunks = split_oversized_chunk(primary_chunk, max_chars=MAX_CHARS, overlap=OVERLAP)

        for sub_chunk in sub_chunks:
            chunk_index += 1
            page_num, search_pos = locate_chunk_page(sub_chunk, full_text, search_pos, page_offsets)

            chunk_id = make_chunk_id("project_management_guide", SOURCE_PATH.name, str(chunk_index))
            payloads.append(
                build_base_payload(
                    text=sub_chunk,
                    chunk_id=chunk_id,
                    doc_type=DOC_TYPE,
                    domain=DOMAIN,
                    source_file=SOURCE_PATH,
                    section=f"부록 {appendix_no}",
                    title=title,
                    applies_to=APPLIES_TO,
                    priority=PRIORITY,
                    chunk_type=chunk_type,
                    keywords=keywords,
                    page=page_num,
                )
            )
    return payloads


def extract_appendix_no(chunk: str) -> str:
    """청크 시작 부분에서 '부록 NN' 형태를 추출."""
    match = re.match(r"부록\s*(\d{2})", chunk)
    return match.group(1) if match else ""


def main():
    ensure_named_collection(COLLECTION_NAME, recreate=False)
    payloads = extract_payloads()
    print(f"[EXTRACTED] project management guide chunks={len(payloads)}")
    upsert_payloads(payloads, COLLECTION_NAME)


if __name__ == "__main__":
    main()