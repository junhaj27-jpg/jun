"""
  - chunk_size 기본값 500자로 조정
  - overlap 기본값 80자로 조정
  - 섹션 헤더 단독으로도 분할 트리거
  - 요구사항 ID 패턴 단독 등장 시 분할
  - 너무 짧은 청크(30자 미만) 병합 처리
"""
import re
from typing import List
from processors.section_detector import is_section_line


def split_into_chunks(
    text: str,
    chunk_size: int = 1000,   
    overlap: int = 150        
) -> List[str]:
    """
    섹션 헤더 / 요구사항 ID 기반 의미 단위 청커.
    chunk_size 이하로 유지하면서, 문맥 경계에서 우선 분할.
    """
    if not text:
        return []

    lines = text.split("\n")
    paragraphs = []
    current_para = []

    # 요구사항 고유번호 패턴 (SFR-001, REQ-01 등)
    PATTERN_STR = r"\b((?:sfr|req|sir|cor|cmr|fqr|sec|per|ast|gcl|isr|dar|wtr|uor|prm|ops|mng)-?\d+|[A-Z]{2,}[-_]?\d{2,5})"

    REQ_ID_PATTERN = re.compile(PATTERN_STR, re.IGNORECASE)
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        is_new_req = bool(re.search(REQ_ID_PATTERN, stripped.lower()))
        is_section  = is_section_line(stripped)

        # ✅ 수정: 섹션 OR 요구사항 ID 단독으로 분할 트리거 (AND 조건 제거)
        if is_section or is_new_req:
            if current_para:
                paragraphs.append("\n".join(current_para))
                current_para = []

        current_para.append(stripped)

    if current_para:
        paragraphs.append("\n".join(current_para))

    # 단락 → 청크 조립
    chunks = []
    current_chunk = []
    current_length = 0

    for para in paragraphs:
        para_len = len(para)

        # 청크 크기 초과 시 마감
        if current_length + para_len + 1 > chunk_size:
            if current_chunk:
                chunks.append("\n".join(current_chunk))

            # 오버랩 버퍼
            overlap_buf = []
            overlap_len = 0
            for prev in reversed(current_chunk):
                if overlap_len + len(prev) + 1 <= overlap:
                    overlap_buf.insert(0, prev)
                    overlap_len += len(prev) + 1
                else:
                    break

            current_chunk = overlap_buf
            current_length = overlap_len

        current_chunk.append(para)
        current_length += para_len + 1

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    # ✅ 추가: 30자 미만 너무 짧은 청크는 앞 청크에 병합
    merged = []
    for chunk in chunks:
        if len(chunk.strip()) < 30 and merged:
            merged[-1] += "\n" + chunk
        else:
            merged.append(chunk)

    return merged
