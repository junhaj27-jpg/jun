import re


def split_by_pattern(
    text: str,
    pattern: str,
    *,
    min_chars: int = 80,
) -> list[str]:
    """
    정규식 패턴을 경계로 텍스트를 분할.
    패턴 매칭 지점부터 다음 매칭 지점 전까지를 하나의 청크로 묶음.
    패턴이 매칭되지 않으면 전체 텍스트를 하나의 청크로 반환.
    """
    matches = list(re.finditer(pattern, text))
    if not matches:
        return [text.strip()] if len(text.strip()) >= min_chars else []

    chunks = []
    # 첫 매칭 이전 텍스트도 보존 (필요 시)
    if matches[0].start() > 0:
        prefix = text[: matches[0].start()].strip()
        if len(prefix) >= min_chars:
            chunks.append(prefix)

    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        if len(chunk) >= min_chars:
            chunks.append(chunk)

    return chunks


def split_oversized_chunk(
    text: str,
    *,
    max_chars: int = 1500,
    overlap: int = 150,
    min_chars: int = 80,
) -> list[str]:
    """
    하나의 청크가 max_chars를 초과하면 슬라이딩 윈도우로 추가 분할.
    """
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        chunk = text[start : start + max_chars].strip()
        if len(chunk) >= min_chars:
            chunks.append(chunk)
        start += max_chars - overlap
    return chunks


def chunk_text_by_pattern(
    text: str,
    pattern: str,
    *,
    min_chars: int = 80,
    max_chars: int = 1500,
    overlap: int = 150,
) -> list[str]:
    """패턴 기반 분할 + 초과 시 슬라이딩 윈도우 보조 분할."""
    primary_chunks = split_by_pattern(text, pattern, min_chars=min_chars)
    result = []
    for chunk in primary_chunks:
        result.extend(split_oversized_chunk(chunk, max_chars=max_chars, overlap=overlap, min_chars=min_chars))
    return result