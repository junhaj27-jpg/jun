import os
import re
import uuid
from pathlib import Path
from typing import Any, Iterable

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv():
        return False

load_dotenv()

DATA_ROOT = Path(os.getenv("INTERFACE_REFERENCE_ROOT", "./data/interface_reference"))
COLLECTION_NAME = os.getenv("ALPLED_REFERENCE_COLLECTION", "ALPLED_reference")
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}
MIN_INCLUDED_PAGE = int(os.getenv("INTERFACE_UIUX_MIN_PAGE", "43"))

INCLUDED_SECTION_RULES = [
    ("design_principle", "디자인 원칙"),
    ("layout_rule", "스타일 가이드 / 배치"),
    ("icon_rule", "스타일 가이드 / 아이콘"),
    ("identity_component", "컴포넌트 / 아이덴티티 / 헤더"),
    ("navigation_component", "컴포넌트 / 탐색 /"),
    ("layout_component", "컴포넌트 / 레이아웃·표현 / 구조화 목록"),
    ("layout_component", "컴포넌트 / 레이아웃·표현 / 모달"),
    ("layout_component", "컴포넌트 / 레이아웃·표현 / 탭"),
    ("layout_component", "컴포넌트 / 레이아웃·표현 / 표"),
    ("action_component", "컴포넌트 / 액션 /"),
    ("selection_component", "컴포넌트 / 선택 /"),
    ("feedback_component", "컴포넌트 / 피드백 / 단계 표시기"),
    ("help_component", "컴포넌트 / 도움 /"),
    ("input_component", "컴포넌트 / 입력 /"),
    ("service_pattern", "서비스 패턴 / 검색 /"),
    ("service_pattern", "서비스 패턴 / 로그인 /"),
]


def normalize_text(value: Any) -> str:
    text = str(value if value is not None else "").replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def split_text(text: str, chunk_size: int = 900, overlap: int = 120) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        chunk = text[start : start + chunk_size].strip()
        if len(chunk) >= 80:
            chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


def iter_source_files() -> Iterable[Path]:
    if not DATA_ROOT.exists():
        print(f"[SKIP] interface reference root not found: {DATA_ROOT}")
        return
    for path in sorted(DATA_ROOT.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield path


def read_pdf(path: Path) -> Iterable[tuple[int, str]]:
    try:
        import fitz

        doc = fitz.open(path)
        try:
            for idx, page in enumerate(doc, start=1):
                text = normalize_text(page.get_text())
                if text:
                    yield idx, text
        finally:
            doc.close()
        return
    except ModuleNotFoundError:
        pass

    try:
        from pypdf import PdfReader
    except ModuleNotFoundError as exc:
        raise RuntimeError("PyMuPDF or pypdf is required to ingest PDF files.") from exc

    reader = PdfReader(str(path))
    for idx, page in enumerate(reader.pages, start=1):
        text = normalize_text(page.extract_text() or "")
        if text:
            yield idx, text


def read_text_file(path: Path) -> Iterable[tuple[int, str]]:
    for encoding in ("utf-8", "utf-8-sig", "cp949", "euc-kr"):
        try:
            text = normalize_text(path.read_text(encoding=encoding))
            if text:
                yield 1, text
            return
        except UnicodeDecodeError:
            continue
    raise UnicodeError(f"Unsupported text encoding: {path}")


def read_document(path: Path) -> Iterable[tuple[int, str]]:
    if path.suffix.lower() == ".pdf":
        return read_pdf(path)
    return read_text_file(path)


def classify_section(text: str) -> tuple[str, str] | None:
    for doc_type, marker in INCLUDED_SECTION_RULES:
        if marker in text:
            return doc_type, marker
    return None


def build_payload(
    *,
    text: str,
    chunk_id: str,
    source_file: Path,
    page: int,
    chunk_index: int,
    doc_type: str,
    section: str,
) -> dict[str, Any]:
    title = extract_title(text, section)
    return {
        "text": text,
        "chunk_id": chunk_id,
        "doc_type": doc_type,
        "domain": "interface",
        "source_name": source_file.stem,
        "section": section,
        "title": title,
        "applies_to": "interface_design,prototype_analysis,ui_component_analysis",
        "priority": "reference",
        "source_file": source_file.name,
        "version": "",
        "chunk_type": "uiux_guideline",
        "keywords": build_keywords(text, section, doc_type),
        "is_active": True,
        "language": "ko",
        "page": page,
        "chunk_index": chunk_index,
    }


def extract_title(text: str, section: str) -> str:
    title_patterns = [
        r"\d{2}\.\s*([^()]{1,30}\([^)]{1,40}\))",
        r"컴포넌트\s*/\s*([^0-9]{1,60})",
        r"서비스 패턴\s*/\s*([^0-9]{1,60})",
        r"스타일 가이드\s*/\s*([^0-9]{1,60})",
    ]
    for pattern in title_patterns:
        match = re.search(pattern, text)
        if match:
            return normalize_text(match.group(1))
    return section


def build_keywords(text: str, section: str, doc_type: str) -> list[str]:
    seeds = [
        "UI",
        "UX",
        "사용자 인터페이스",
        "화면설계서",
        section,
        doc_type,
    ]
    ui_terms = [
        "헤더",
        "메뉴",
        "브레드크럼",
        "사이드 메뉴",
        "검색",
        "표",
        "목록",
        "탭",
        "모달",
        "버튼",
        "링크",
        "입력",
        "체크박스",
        "라디오",
        "셀렉트",
        "페이지네이션",
        "단계 표시기",
        "도움말",
        "로그인",
    ]
    seeds.extend(term for term in ui_terms if term in text)
    return sorted(set(seeds))


def extract_payloads() -> list[dict[str, Any]]:
    payloads = []
    for source_file in iter_source_files():
        print(f"[PROCESS] {source_file}")
        for page, page_text in read_document(source_file):
            if source_file.suffix.lower() == ".pdf" and page < MIN_INCLUDED_PAGE:
                continue
            classified = classify_section(page_text)
            if not classified:
                continue
            doc_type, section = classified
            for chunk_index, chunk in enumerate(split_text(page_text), start=1):
                base = f"{source_file.name}:{page}:{chunk_index}:{section}"
                chunk_id = f"interface_uiux_{uuid.uuid5(uuid.NAMESPACE_DNS, base)}"
                payloads.append(
                    build_payload(
                        text=chunk,
                        chunk_id=chunk_id,
                        source_file=source_file,
                        page=page,
                        chunk_index=chunk_index,
                        doc_type=doc_type,
                        section=section,
                    )
                )
    return payloads


def upsert_payloads(payloads: list[dict[str, Any]], batch_size: int = 32) -> None:
    from qdrant_client.models import PointStruct

    from rag.qdrant_config import get_client, get_embedder

    try:
        from tqdm import tqdm
    except ModuleNotFoundError:
        tqdm = lambda value: value

    client = get_client()
    embedder = get_embedder()

    for start in tqdm(range(0, len(payloads), batch_size)):
        batch = payloads[start : start + batch_size]
        vectors = embedder.encode(
            [payload["text"] for payload in batch],
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

    print(f"[DONE] collection={COLLECTION_NAME}, chunks={len(payloads)}")


def main() -> None:
    from rag.qdrant_config import ensure_named_collection

    ensure_named_collection(COLLECTION_NAME, recreate=False)
    payloads = extract_payloads()
    print(f"[EXTRACTED] interface UIUX chunks={len(payloads)}")
    upsert_payloads(payloads)


if __name__ == "__main__":
    main()
