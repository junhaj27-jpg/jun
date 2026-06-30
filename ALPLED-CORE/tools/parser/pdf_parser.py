from pathlib import Path

from tools.result import ToolResult, error_result, success_result


def parse_pdf(file_path: str) -> ToolResult:
    try:
        import fitz

        path = Path(file_path).resolve(strict=True)
        pages = []
        with fitz.open(str(path)) as document:
            for index, page in enumerate(document):
                text = page.get_text("text")
                pages.append({"page_number": index + 1, "text": text})
        return success_result(
            {
                "file_path": str(path),
                "text": "\n".join(page["text"] for page in pages),
                "pages": pages,
            }
        )
    except Exception as exc:
        return error_result("PDF_PARSE_FAILED", str(exc), {"file_path": file_path})
