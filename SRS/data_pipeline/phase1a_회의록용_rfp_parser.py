import os
from pathlib import Path

# PDF
import pdfplumber

# DOCX
import docx2txt

# fallback (옵션)
try:
    import pytesseract
    from pdf2image import convert_from_path
    OCR_AVAILABLE = True
except:
    OCR_AVAILABLE = False


# ─────────────────────────────────────────────
# 1. PDF Reader (핵심)
# ─────────────────────────────────────────────
def read_pdf(file_path: str, max_chars: int = 10000) -> str:
    """
    PDF 텍스트 추출 (text layer + fallback OCR)
    """

    text_chunks = []

    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()

            if page_text:
                text_chunks.append(page_text)

    text = "\n".join(text_chunks).strip()

    # 너무 비어있으면 OCR fallback
    if len(text) < 200 and OCR_AVAILABLE:
        print("⚠️ PDF 텍스트 부족 → OCR 모드 실행")

        images = convert_from_path(file_path)
        ocr_texts = []

        for img in images:
            ocr_texts.append(pytesseract.image_to_string(img, lang="kor+eng"))

        text = "\n".join(ocr_texts)

    # 길이 제한
    return text[:max_chars]


# ─────────────────────────────────────────────
# 2. DOCX Reader
# ─────────────────────────────────────────────
def read_docx(file_path: str, max_chars: int = 10000) -> str:
    text = docx2txt.process(file_path)
    return text[:max_chars]


# ─────────────────────────────────────────────
# 3. TXT Reader
# ─────────────────────────────────────────────
def read_txt(file_path: str, max_chars: int = 10000) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()[:max_chars]


# ─────────────────────────────────────────────
# 4. Unified Reader (핵심 entry)
# ─────────────────────────────────────────────
def read_document(file_path: str, max_chars: int = 10000) -> str:
    """
    PDF / DOCX / TXT 자동 분기
    """

    ext = Path(file_path).suffix.lower()

    print(f"📄 문서 로딩: {file_path}")

    if ext == ".pdf":
        text = read_pdf(file_path, max_chars=max_chars)

    elif ext in [".docx", ".doc"]:
        text = read_docx(file_path, max_chars=max_chars)

    elif ext in [".txt"]:
        text = read_txt(file_path, max_chars=max_chars)

    else:
        raise ValueError(f"지원하지 않는 파일 형식: {ext}")

    # 기본 정리 (중요)
    text = normalize_text(text)

    print(f"   → 추출 완료: {len(text):,} chars")

    return text


# ─────────────────────────────────────────────
# 5. Text Normalizer (RFP 품질 핵심)
# ─────────────────────────────────────────────
def normalize_text(text: str) -> str:
    """
    RFP 문서 정리:
    - 연속 공백 제거
    - 깨진 줄 정리
    - 불필요 특수문자 감소
    """

    import re

    text = re.sub(r"\n{3,}", "\n\n", text)   # 빈 줄 정리
    text = re.sub(r"[ \t]{2,}", " ", text)   # 공백 정리
    text = text.replace("\x00", "")          # null 제거

    return text.strip()