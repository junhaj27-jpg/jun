"""템플릿 payload를 DOCX 파일로 생성합니다."""

import json
import zipfile
from pathlib import Path
from typing import Any

from docx import Document
from docx.shared import Inches

from tools.result import ToolResult, error_result, success_result


def export_docx(
    export_payload: dict[str, Any],
    output_path: str,
    *,
    template_path: str | None = None,
) -> ToolResult:
    """유효한 템플릿이 있으면 사용하고, 없으면 기본 문서를 생성합니다."""

    try:
        target = Path(output_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        template = Path(template_path).resolve() if template_path else None
        document = (
            Document(str(template))
            if template and template.is_file() and zipfile.is_zipfile(template)
            else Document()
        )

        document.add_heading(str(export_payload.get("title", "산출물")), level=0)
        for section_name, section_value in export_payload.get("content", {}).items():
            document.add_heading(section_name, level=1)
            _append_value(document, section_value)

        for image_path in export_payload.get("image_paths", []):
            image = Path(str(image_path))
            if image.is_file():
                document.add_picture(str(image), width=Inches(6.0))

        document.save(target)
        return success_result(
            {
                "local_file_path": str(target),
                "file_name": target.name,
                "file_size": target.stat().st_size,
            }
        )
    except Exception as exc:
        return error_result("DOCX_EXPORT_FAILED", str(exc))


def _append_value(document: Any, value: Any) -> None:
    if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
        keys = list(dict.fromkeys(key for item in value for key in item))
        table = document.add_table(rows=1, cols=len(keys))
        for index, key in enumerate(keys):
            table.rows[0].cells[index].text = str(key)
        for item in value:
            cells = table.add_row().cells
            for index, key in enumerate(keys):
                cells[index].text = _to_text(item.get(key))
        return
    document.add_paragraph(_to_text(value))


def _to_text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return "" if value is None else str(value)
