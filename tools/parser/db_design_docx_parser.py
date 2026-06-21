# DB 설계서 DOCX의 테이블 명세 표를 구조화된 JSON으로 추출합니다.

from pathlib import Path
from typing import Any

from tools.result import ToolResult, error_result, success_result


def parse_db_design_docx(file_path: str) -> ToolResult:
    try:
        from docx import Document

        path = Path(file_path).resolve(strict=True)
        document = Document(str(path))
        tables = [_parse_table_spec(table) for table in document.tables]
        parsed_tables = [table for table in tables if table]
        return success_result(
            {
                "file_path": str(path),
                "tables": parsed_tables,
                "items": parsed_tables,
                "db_design_json": {"tables": parsed_tables},
            }
        )
    except Exception as exc:
        return error_result("DB_DOCX_PARSE_FAILED", str(exc), {"file_path": file_path})


def _parse_table_spec(docx_table: Any) -> dict[str, Any] | None:
    rows = [[_clean(cell.text) for cell in row.cells] for row in docx_table.rows]
    if not _looks_like_db_table_spec(rows):
        return None

    header_index = _find_header_row(rows, "컬럼명", "컬럼 ID", "타입 및 길이")
    if header_index is None:
        return None

    table_id = _value_after_label(rows, "테이블 ID")
    table_name = _value_after_label(rows, "테이블명") or table_id
    database_name = _value_after_label(rows, "데이터베이스 명")
    tablespace_name = _value_after_label(rows, "TS명")
    trigger_config = _value_after_label(rows, "트리거 구성")
    table_description = _value_after_label(rows, "테이블 설명")

    volume_values = _values_after_header(rows, ("초기건수", "증가량(일)", "보관주기", "최대건수", "용량", "비고"))
    columns = _parse_columns(rows[header_index:])

    if not table_id and not table_name and not columns:
        return None

    return {
        "table_id": table_id or table_name,
        "table_name": table_id or table_name,
        "table_logical_name": table_name or table_id,
        "database_name": database_name or "업무 DB",
        "tablespace_name": tablespace_name or "",
        "trigger_config": trigger_config or "해당 없음",
        "table_description": table_description or f"{table_name or table_id} 정보를 관리하는 테이블입니다.",
        "initial_count": volume_values.get("초기건수", "0"),
        "daily_growth": volume_values.get("증가량(일)", "산정 필요"),
        "retention_period": volume_values.get("보관주기", "업무 기준에 따름"),
        "max_count": volume_values.get("최대건수", "산정 필요"),
        "capacity": volume_values.get("용량", "산정 필요"),
        "note": volume_values.get("비고", ""),
        "columns": columns,
    }


def _looks_like_db_table_spec(rows: list[list[str]]) -> bool:
    joined = "\n".join("\t".join(row) for row in rows)
    return "테이블 ID" in joined and "컬럼 ID" in joined and "타입 및 길이" in joined


def _find_header_row(rows: list[list[str]], *headers: str) -> int | None:
    for index, row in enumerate(rows):
        cells = set(row)
        if all(header in cells for header in headers):
            return index
    return None


def _value_after_label(rows: list[list[str]], label: str) -> str:
    for row in rows:
        for index, value in enumerate(row):
            if value != label:
                continue
            for candidate in row[index + 1 :]:
                if candidate and candidate != label and candidate not in _KNOWN_LABELS:
                    return candidate
    return ""


def _values_after_header(rows: list[list[str]], headers: tuple[str, ...]) -> dict[str, str]:
    header_index = None
    for index, row in enumerate(rows):
        if all(header in row for header in headers[:-1]):
            header_index = index
            break
    if header_index is None or header_index + 1 >= len(rows):
        return {}

    header_row = rows[header_index]
    value_row = rows[header_index + 1]
    values: dict[str, str] = {}
    for column_index, header in enumerate(header_row):
        if header in headers and header not in values:
            values[header] = value_row[column_index] if column_index < len(value_row) else ""
    return values


def _parse_columns(rows_from_header: list[list[str]]) -> list[dict[str, Any]]:
    if not rows_from_header:
        return []
    header = rows_from_header[0]
    header_map = {name: index for index, name in enumerate(header) if name}
    columns = []
    for row in rows_from_header[1:]:
        column_logical_name = _cell(row, header_map, "컬럼명")
        column_name = _cell(row, header_map, "컬럼 ID")
        type_and_length = _cell(row, header_map, "타입 및 길이")
        if not any((column_logical_name, column_name, type_and_length)):
            continue
        not_null = _yes(_cell(row, header_map, "Not Null"))
        pk = _yes(_cell(row, header_map, "PK"))
        fk = _yes(_cell(row, header_map, "FK"))
        idx = _yes(_cell(row, header_map, "IDX") or _cell(row, header_map, "INX"))
        default = _cell(row, header_map, "기본값")
        constraint = _cell(row, header_map, "제약조건")
        constraints = []
        if pk:
            constraints.append("PK")
        if fk:
            constraints.append("FK")
        if idx:
            constraints.append("IDX")
        if constraint:
            constraints.append(constraint)
        data_type, length = _split_type_and_length(type_and_length)
        columns.append(
            {
                "column_name": column_name or column_logical_name,
                "column_id": column_name or column_logical_name,
                "column_logical_name": column_logical_name or column_name,
                "data_type": data_type or type_and_length or "VARCHAR(255)",
                "type_and_length": type_and_length or data_type or "VARCHAR(255)",
                "length": length,
                "nullable": not not_null,
                "not_null": "Y" if not_null else "",
                "pk": "Y" if pk else "",
                "fk": "Y" if fk else "",
                "idx": "Y" if idx else "",
                "default": default,
                "description": column_logical_name or column_name,
                "constraint": constraint,
                "constraints": constraints,
            }
        )
    return columns


def _cell(row: list[str], header_map: dict[str, int], key: str) -> str:
    index = header_map.get(key)
    if index is None or index >= len(row):
        return ""
    return row[index]


def _yes(value: str) -> bool:
    return str(value).strip().upper() in {"Y", "YES", "TRUE", "1", "PK", "FK", "IDX", "INX"}


def _split_type_and_length(value: str) -> tuple[str, str]:
    text = str(value or "").strip()
    if "(" not in text or ")" not in text:
        return text, ""
    data_type = text.split("(", 1)[0].strip()
    length = text.split("(", 1)[1].split(")", 1)[0].strip()
    return data_type, length


def _clean(value: str) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


_KNOWN_LABELS = {
    "테이블 ID",
    "테이블명",
    "데이터베이스 명",
    "TS명",
    "트리거 구성",
    "테이블 설명",
    "초기건수",
    "증가량(일)",
    "보관주기",
    "최대건수",
    "용량",
    "비고",
    "컬럼명",
    "컬럼 ID",
    "타입 및 길이",
    "Not Null",
    "PK",
    "FK",
    "IDX",
    "INX",
    "기본값",
    "제약조건",
}
