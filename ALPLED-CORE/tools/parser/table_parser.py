from collections.abc import Callable
from pathlib import Path
from typing import Any

from tools.parser.docx_parser import parse_docx
from tools.result import ToolResult, error_result, success_result


TableParser = Callable[[str], Any]


def parse_tables(
    file_path: str,
    *,
    parser: TableParser | None = None,
) -> ToolResult:
    """문서 표 추출 진입점입니다. 현재 DOCX 표와 주입된 Parser를 지원합니다."""

    if parser is not None:
        try:
            return success_result({"file_path": file_path, "tables": parser(file_path)})
        except Exception as exc:
            return error_result("TABLE_PARSE_FAILED", str(exc), {"file_path": file_path})

    if Path(file_path).suffix.lower() == ".docx":
        result = parse_docx(file_path)
        if result["success"]:
            return success_result(
                {"file_path": file_path, "tables": result["data"]["tables"]}
            )
        return result

    # TODO: PDF 표 추출 Parser가 확정되면 확장합니다.
    return error_result(
        "TABLE_PARSER_NOT_IMPLEMENTED",
        "해당 문서 형식의 표 Parser는 아직 구현되지 않았습니다.",
        {"file_path": file_path},
    )
