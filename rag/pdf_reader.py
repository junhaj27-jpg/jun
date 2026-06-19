import re
from pathlib import Path
from typing import Iterable

import fitz


def clean_text(text: str, *, min_line_chars: int = 3) -> str:
    """PDF 추출 텍스트의 노이즈 제거.

    min_line_chars: 이 값 이하 길이(공백 제거 후)의 단독 줄을 노이즈로
    간주해 제거한다 (페이지 번호, 머리글/바닥글 등). 기본값 3 (기존 동작과 동일).
    챕터 번호("01" 등 2자리 숫자 단독 줄)가 제거되면 안 되는 문서는
    더 작은 값(예: 1)을 전달한다.
    """
    # 특수문자 반복 라인 제거 (구분선 등)
    text = re.sub(r"[─═━\-=\*\.]{4,}", "", text)

    # min_line_chars 이하 단독 줄 제거 (페이지 번호, 머리글/바닥글)
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if len(stripped) > min_line_chars or stripped == "":
            lines.append(line)
    text = "\n".join(lines)

    # 다중 공백 정리
    text = re.sub(r"[ \t]{4,}", " ", text)
    # 연속 빈 줄 압축
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def read_pdf_pages(
    path: Path,
    *,
    page_filter=None,  # callable: (page_num: int) -> bool
    min_line_chars: int = 3,
) -> Iterable[tuple[int, str]]:
    """
    PDF를 페이지 단위로 읽어서 (페이지번호, 정제된 텍스트) 튜플을 yield.

    page_filter가 주어지면 해당 조건을 만족하는 페이지만 처리.
    min_line_chars는 clean_text()에 그대로 전달된다 (기본값 3 = 기존 동작과 동일).
    """
    doc = fitz.open(path)
    try:
        for page_num, page in enumerate(doc, start=1):
            if page_filter and not page_filter(page_num):
                continue
            text = page.get_text()
            if not text.strip():
                continue
            yield page_num, clean_text(text, min_line_chars=min_line_chars)
    finally:
        doc.close()