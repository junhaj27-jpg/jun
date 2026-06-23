from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from agents.approval_review.processors.json_loader import parse_content_text
from tools.result import ToolResult
from tools.storage.downloader import download_file


DetailDownloader = Callable[..., ToolResult]


def load_detail_content(
    detail: dict[str, Any],
    *,
    downloader: DetailDownloader = download_file,
) -> dict[str, Any]:
    blob = detail.get("docs_dtl_cn")
    if blob not in (None, b"", ""):
        if isinstance(blob, memoryview):
            blob = blob.tobytes()
        if isinstance(blob, bytes):
            try:
                text = blob.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(
                    f"docs_dtl_cn UTF-8 decode failed: {detail.get('docs_dtl_sn')}"
                ) from exc
        else:
            text = str(blob)
        return parse_content_text(text)

    docs_path = str(detail.get("docs_path") or "").strip()
    if not docs_path:
        raise ValueError(
            f"detail content and docs_path are empty: {detail.get('docs_dtl_sn')}"
        )

    local_path = _resolve_local_path(docs_path, downloader)
    suffix = local_path.suffix.lower()
    if suffix == ".docx":
        return {
            "content_type": "document",
            "data": _parse_docx(local_path, docs_path),
        }
    if suffix == ".pdf":
        return {
            "content_type": "document",
            "data": _parse_pdf(local_path, docs_path),
        }

    try:
        text = local_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"docs_path read failed: {docs_path}") from exc
    return parse_content_text(text)


def _resolve_local_path(
    docs_path: str,
    downloader: DetailDownloader,
) -> Path:
    if docs_path.startswith("s3://"):
        parsed = urlparse(docs_path)
        result = downloader(
            s3_key=parsed.path.lstrip("/"),
            s3_bucket=parsed.netloc,
            file_name=Path(parsed.path).name,
        )
        return _downloaded_path(result, docs_path)
    if docs_path.startswith(("http://", "https://")):
        result = downloader(
            file_path=docs_path,
            file_name=Path(urlparse(docs_path).path).name,
        )
        return _downloaded_path(result, docs_path)
    try:
        return Path(docs_path).resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"docs_path read failed: {docs_path}") from exc


def _downloaded_path(result: ToolResult, docs_path: str) -> Path:
    if not result["success"]:
        error = result.get("error") or {}
        message = error.get("message") or "download failed"
        raise ValueError(f"docs_path download failed: {docs_path}: {message}")
    local_file_path = (result.get("data") or {}).get("local_file_path")
    if not local_file_path:
        raise ValueError(f"docs_path download result is empty: {docs_path}")
    return Path(str(local_file_path))


def _parse_docx(local_path: Path, docs_path: str) -> dict[str, Any]:
    word_namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    namespaces = {"w": word_namespace}
    try:
        with ZipFile(local_path) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
    except (OSError, BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise ValueError(f"docs_path parse failed: {docs_path}: {exc}") from exc

    paragraphs = [
        text
        for paragraph in root.findall(".//w:body/w:p", namespaces)
        if (text := _word_text(paragraph, word_namespace))
    ]
    tables: list[list[list[str]]] = []
    for table in root.findall(".//w:body/w:tbl", namespaces):
        rows = []
        for row in table.findall("./w:tr", namespaces):
            rows.append(
                [
                    _word_text(cell, word_namespace)
                    for cell in row.findall("./w:tc", namespaces)
                ]
            )
        tables.append(rows)
    return {
        "paragraphs": paragraphs,
        "tables": tables,
    }


def _word_text(element: ElementTree.Element, namespace: str) -> str:
    values = [
        node.text or ""
        for node in element.iter(f"{{{namespace}}}t")
    ]
    return "".join(values).strip()


def _parse_pdf(local_path: Path, docs_path: str) -> dict[str, Any]:
    try:
        import fitz

        document = fitz.open(local_path)
        pages = [page.get_text().strip() for page in document]
        document.close()
    except Exception as exc:
        raise ValueError(f"docs_path parse failed: {docs_path}: {exc}") from exc
    return {
        "pages": pages,
    }
