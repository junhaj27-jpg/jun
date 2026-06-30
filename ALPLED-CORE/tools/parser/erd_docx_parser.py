# ERD DOCX 문서의 엔티티/속성 표를 DB 설계 입력용 JSON으로 변환합니다.

from pathlib import Path
import re
from typing import Any

from agents.data_structure_design.processors.column_standardizer import (
    standardize_name,
    table_name,
)
from tools.parser.docx_parser import parse_docx
from tools.result import ToolResult, error_result, success_result


def parse_erd_docx(file_path: str) -> ToolResult:
    parsed = parse_docx(file_path)
    if not parsed["success"]:
        return parsed

    raw_tables = parsed["data"].get("tables") or []
    tables = extract_erd_tables(raw_tables)
    if not tables:
        return error_result(
            "ERD_DOCX_TABLES_NOT_FOUND",
            "ERD DOCX에서 엔티티/속성 표를 찾지 못했습니다.",
            {"file_path": str(Path(file_path))},
        )
    return success_result(
        {
            "file_path": parsed["data"].get("file_path", str(Path(file_path))),
            "tables": tables,
        }
    )


def extract_erd_tables(raw_tables: list[Any]) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    pending_columns: list[dict[str, Any]] = []

    for raw_table in raw_tables:
        rows = _clean_rows(raw_table)
        if not rows:
            continue

        entity = _parse_alpled_entity_table(rows)
        if entity:
            entities.append(entity)
            continue

        entity_rows = _parse_horizontal_entity_table(rows)
        if entity_rows:
            entities.extend(entity_rows)
            continue

        column_rows = _parse_horizontal_column_table(rows)
        if column_rows:
            pending_columns.extend(column_rows)

    _attach_pending_columns(entities, pending_columns)
    return [_normalize_entity(index, entity) for index, entity in enumerate(entities, start=1)]


def _parse_alpled_entity_table(rows: list[list[str]]) -> dict[str, Any] | None:
    if len(rows) < 4:
        return None
    if max(len(row) for row in rows) < 8:
        return None

    if _cell(rows, 0, 0) != "엔티티 ID" or _cell(rows, 0, 5) != "엔티티명":
        return None

    entity_id = _first_distinct_after_label(rows[0], "엔티티 ID")
    entity_name = _first_distinct_after_label(rows[0], "엔티티명")
    description = _first_distinct_after_label(rows[1], "엔티티 설명")
    if not (entity_id or entity_name or description):
        return None

    logical_name = entity_name or _description_subject(description) or entity_id
    columns = [
        column
        for row_index, row in enumerate(rows[3:], start=1)
        if (column := _parse_alpled_column_row(row, row_index))
    ]
    return {
        "entity_id": entity_id,
        "table_id": entity_id if _looks_like_table_id(entity_id) else "",
        "logical_name": logical_name,
        "physical_name": table_name(logical_name),
        "description": description,
        "table_description": description,
        "columns": columns,
    }


def _parse_alpled_column_row(row: list[str], row_index: int) -> dict[str, Any] | None:
    values = [value.strip() for value in row]
    if not any(values):
        return None
    if _is_headerish(" ".join(values)):
        return None

    logical_name = values[0] if len(values) > 0 else ""
    synonym = values[1] if len(values) > 1 else ""
    data_type = values[2] if len(values) > 2 else ""
    length = values[3] if len(values) > 3 else ""
    not_null = values[4] if len(values) > 4 else ""
    pk = values[5] if len(values) > 5 else ""
    fk = values[6] if len(values) > 6 else ""
    idx = values[7] if len(values) > 7 else ""
    default = values[8] if len(values) > 8 else ""
    constraint = values[9] if len(values) > 9 else ""

    if not (logical_name or data_type):
        return None

    constraints = []
    if _is_yes(pk) or "PK" in pk.upper():
        constraints.append("PK")
    if _is_yes(fk) or "FK" in fk.upper():
        constraints.append("FK")
    if _is_yes(idx) or "IN" in idx.upper():
        constraints.append("IDX")
    if constraint and constraint not in constraints:
        constraints.append(constraint)

    data_type = _merge_type_and_length(data_type, length)
    physical_name = standardize_name(logical_name, fallback=f"column_{row_index}")
    return {
        "column_id": f"COL-{row_index:03d}",
        "logical_name": logical_name or physical_name,
        "synonym": "" if synonym in {"-", "–", "—", "없음", "해당 없음"} else synonym,
        "physical_name": physical_name,
        "data_type": data_type or "VARCHAR(255)",
        "nullable": not _is_yes(not_null),
        "default": default or None,
        "constraints": constraints,
        "description": logical_name or physical_name,
    }


def _parse_horizontal_entity_table(rows: list[list[str]]) -> list[dict[str, Any]]:
    header_index = _find_header_index(rows, ("엔티티", "테이블", "논리명"), ("id", "물리명", "명"))
    if header_index is None:
        return []
    headers = [_key(cell) for cell in rows[header_index]]
    if not _has_any(headers, ("엔티티명", "테이블명", "논리명", "logicalname")):
        return []
    if _has_any(headers, ("속성명", "컬럼명", "columnname", "attributename")):
        return []

    entities = []
    for row in rows[header_index + 1 :]:
        mapped = _map_row(headers, row)
        logical_name = _first(mapped, "엔티티명", "테이블명", "논리명", "logicalname", "tablename")
        physical_name = _first(mapped, "엔티티id", "테이블id", "물리명", "physicalname", "tableid")
        description = _first(mapped, "설명", "엔티티설명", "테이블설명", "description")
        if not (logical_name or physical_name or description):
            continue
        entities.append(
            {
                "entity_id": _first(mapped, "entityid", "엔티티id") or "",
                "table_id": _first(mapped, "tableid", "테이블id") or "",
                "logical_name": logical_name or physical_name,
                "physical_name": physical_name if _looks_physical_name(physical_name) else "",
                "description": description,
                "table_description": description,
                "columns": [],
            }
        )
    return entities


def _parse_horizontal_column_table(rows: list[list[str]]) -> list[dict[str, Any]]:
    header_index = _find_header_index(rows, ("속성", "컬럼", "column"), ("타입", "type", "id", "명"))
    if header_index is None:
        return []
    headers = [_key(cell) for cell in rows[header_index]]
    if not _has_any(headers, ("속성명", "컬럼명", "논리명", "columnname", "attributename")):
        return []

    columns = []
    for row_index, row in enumerate(rows[header_index + 1 :], start=1):
        mapped = _map_row(headers, row)
        logical_name = _first(mapped, "속성명", "컬럼명", "논리명", "columnname", "attributename")
        physical_name = _first(mapped, "속성id", "컬럼id", "물리명", "physicalname", "columnid")
        data_type = _first(mapped, "데이터타입", "타입", "자료형", "datatype", "type")
        if not (logical_name or physical_name or data_type):
            continue
        pk = _first(mapped, "pk", "기본키")
        fk = _first(mapped, "fk", "외래키")
        constraint = _first(mapped, "제약조건", "constraint", "constraints")
        constraints = []
        if _is_yes(pk) or "PK" in pk.upper():
            constraints.append("PK")
        if _is_yes(fk) or "FK" in fk.upper():
            constraints.append("FK")
        if constraint and constraint not in constraints:
            constraints.append(constraint)
        columns.append(
            {
                "entity_name": _first(mapped, "엔티티명", "테이블명", "logicaltablename", "tablename"),
                "entity_id": _first(mapped, "엔티티id", "테이블id", "tableid"),
                "column_id": _first(mapped, "columnid", "컬럼id", "속성id") or f"COL-{row_index:03d}",
                "logical_name": logical_name or physical_name,
                "physical_name": physical_name,
                "data_type": data_type or "VARCHAR(255)",
                "nullable": _nullable_from_text(_first(mapped, "null", "nullable", "널허용", "null허용")),
                "default": _first(mapped, "default", "기본값") or None,
                "constraints": constraints,
                "description": _first(mapped, "설명", "속성설명", "컬럼설명", "description") or logical_name,
            }
        )
    return columns


def _attach_pending_columns(entities: list[dict[str, Any]], columns: list[dict[str, Any]]) -> None:
    for column in columns:
        target = _find_entity_for_column(entities, column)
        if target is None and len(entities) == 1:
            target = entities[0]
        if target is None:
            continue
        target.setdefault("columns", []).append(column)


def _find_entity_for_column(entities: list[dict[str, Any]], column: dict[str, Any]) -> dict[str, Any] | None:
    column_entity_keys = {
        _norm(column.get("entity_name")),
        _norm(column.get("entity_id")),
    }
    for entity in entities:
        entity_keys = {
            _norm(entity.get("logical_name")),
            _norm(entity.get("physical_name")),
            _norm(entity.get("entity_id")),
            _norm(entity.get("table_id")),
        }
        if column_entity_keys & entity_keys:
            return entity
    return None


def _normalize_entity(index: int, entity: dict[str, Any]) -> dict[str, Any]:
    logical_name = str(entity.get("logical_name") or entity.get("physical_name") or f"테이블 {index}").strip()
    physical_name = str(entity.get("physical_name") or "").strip()
    table_id = str(entity.get("table_id") or f"TABLE-{index:03d}").strip()
    entity_id = str(entity.get("entity_id") or f"ENT-{index:03d}").strip()
    description = str(entity.get("description") or entity.get("table_description") or "").strip()
    table_description = str(entity.get("table_description") or description).strip()
    return {
        **entity,
        "table_id": table_id,
        "entity_id": entity_id,
        "logical_name": logical_name,
        "physical_name": physical_name,
        "description": description,
        "table_description": table_description,
        "columns": [
            _normalize_column(index, column_index, column)
            for column_index, column in enumerate(entity.get("columns") or [], start=1)
            if isinstance(column, dict)
        ],
    }


def _normalize_column(table_index: int, column_index: int, column: dict[str, Any]) -> dict[str, Any]:
    logical_name = str(column.get("logical_name") or column.get("physical_name") or f"컬럼 {column_index}").strip()
    physical_name = str(column.get("physical_name") or "").strip()
    return {
        **column,
        "column_id": str(column.get("column_id") or f"COL-{table_index:03d}-{column_index:03d}"),
        "logical_name": logical_name,
        "physical_name": physical_name,
        "data_type": str(column.get("data_type") or "VARCHAR(255)").strip(),
        "nullable": bool(column.get("nullable", True)),
        "constraints": [item for item in column.get("constraints", []) if item],
        "description": str(column.get("description") or logical_name).strip(),
    }


def _clean_rows(raw_table: Any) -> list[list[str]]:
    rows = []
    if not isinstance(raw_table, list):
        return rows
    for raw_row in raw_table:
        if not isinstance(raw_row, list):
            continue
        row = [_clean_cell(cell) for cell in raw_row]
        if any(row):
            rows.append(row)
    return rows


def _clean_cell(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def _cell(rows: list[list[str]], row_idx: int, col_idx: int) -> str:
    if row_idx >= len(rows) or col_idx >= len(rows[row_idx]):
        return ""
    return rows[row_idx][col_idx].strip()


def _first_distinct_after_label(row: list[str], label: str) -> str:
    if label not in row:
        return ""
    start = row.index(label) + 1
    for value in row[start:]:
        text = str(value or "").strip()
        if text and text != label:
            return text
    return ""


def _description_subject(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    text = re.sub(r"(정보를\s*)?관리하는\s*(테이블|엔티티)입니다\.?$", "", text).strip()
    return text


def _find_header_index(rows: list[list[str]], *groups: tuple[str, ...]) -> int | None:
    for index, row in enumerate(rows[:5]):
        text = " ".join(row).lower()
        if all(any(token.lower() in text for token in group) for group in groups):
            return index
    return None


def _map_row(headers: list[str], row: list[str]) -> dict[str, str]:
    return {header: row[index].strip() if index < len(row) else "" for index, header in enumerate(headers)}


def _key(value: Any) -> str:
    return re.sub(r"[\s_\-()/\[\].:]+", "", str(value or "").strip().lower())


def _norm(value: Any) -> str:
    return _key(value)


def _first(mapped: dict[str, str], *keys: str) -> str:
    wanted = {_key(key) for key in keys}
    for key, value in mapped.items():
        if key in wanted and value:
            return value
    return ""


def _has_any(headers: list[str], keys: tuple[str, ...]) -> bool:
    wanted = {_key(key) for key in keys}
    return any(header in wanted for header in headers)


def _is_yes(value: Any) -> bool:
    text = str(value or "").strip().upper()
    return text in {"Y", "YES", "TRUE", "1", "필수", "예", "O", "○"}


def _nullable_from_text(value: Any) -> bool:
    text = str(value or "").strip().upper()
    if text in {"", "Y", "YES", "TRUE", "1", "NULL", "허용", "예", "O", "○"}:
        return True
    if text in {"N", "NO", "FALSE", "0", "NOT NULL", "NOTNULL", "비허용", "필수", "아니오", "X"}:
        return False
    return True


def _merge_type_and_length(data_type: str, length: str) -> str:
    data_type = str(data_type or "").strip()
    length = str(length or "").strip()
    if not length or "(" in data_type:
        return data_type
    if data_type.upper() in {"VARCHAR", "CHAR", "DECIMAL", "NUMBER", "NUMERIC"}:
        return f"{data_type}({length})"
    return data_type


def _looks_like_table_id(value: str) -> bool:
    return bool(re.search(r"(TABLE|TBL|ENT)-?\d+", str(value or ""), re.IGNORECASE))


def _looks_physical_name(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9_]*$", str(value or "").strip()))


def _is_headerish(text: str) -> bool:
    key = _key(text)
    return any(token in key for token in ("속성명", "컬럼명", "datatype", "데이터타입"))
