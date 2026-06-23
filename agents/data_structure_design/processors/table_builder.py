# 추출된 엔티티를 기반으로 ERD 테이블과 DB 명세를 설계합니다.

from copy import deepcopy
import re
from typing import Any

from agents.data_structure_design.processors.column_standardizer import (
    primary_key_name,
    standardize_name,
    table_name,
)
from agents.data_structure_design.db_quality import tablespace_name


def build_erd_tables(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tables = []
    for index, entity in enumerate(entities):
        logical_name = str(entity.get("logical_name") or entity.get("entity_name") or "")
        physical_name = table_name(logical_name)
        pk_name = primary_key_name(logical_name)
        base_name = physical_name.removeprefix("tbl_")
        tables.append(
            {
                "table_id": f"TABLE-{index + 1:03d}",
                "entity_id": str(entity.get("entity_id") or f"ENT-{index + 1:03d}"),
                "related_class_id": str(entity.get("related_class_id") or entity.get("class_id") or ""),
                "related_class_name": str(entity.get("related_class_name") or entity.get("class_name") or ""),
                "logical_name": logical_name,
                "entity_name": logical_name,
                "physical_name": physical_name,
                "table_name": physical_name,
                "description": _table_description(logical_name),
                "entity_description": _table_description(logical_name),
                "table_description": _table_description(logical_name),
                "source_requirement_ids": entity.get("source_requirement_ids", []),
                "columns": [
                    {
                        "column_id": f"COL-{index + 1:03d}-001",
                        "logical_name": f"{logical_name} 일련번호",
                        "attribute_name": f"{logical_name} 일련번호",
                        "physical_name": pk_name,
                        "column_name": pk_name,
                        "data_type": "BIGINT",
                        "nullable": False,
                        "constraints": ["PK"],
                        "description": f"{logical_name} 고유 식별자",
                    },
                    {
                        "column_id": f"COL-{index + 1:03d}-002",
                        "logical_name": f"{logical_name} 명",
                        "attribute_name": f"{logical_name} 명",
                        "physical_name": f"{base_name}_nm",
                        "column_name": f"{base_name}_nm",
                        "data_type": "VARCHAR(200)",
                        "nullable": False,
                        "constraints": [],
                        "description": f"{logical_name} 명칭",
                    },
                    {
                        "column_id": f"COL-{index + 1:03d}-003",
                        "logical_name": f"{logical_name} 내용",
                        "attribute_name": f"{logical_name} 내용",
                        "physical_name": f"{base_name}_cn",
                        "column_name": f"{base_name}_cn",
                        "data_type": "TEXT",
                        "nullable": True,
                        "constraints": [],
                        "description": f"{logical_name} 상세 내용",
                    },
                    {
                        "column_id": f"COL-{index + 1:03d}-004",
                        "logical_name": f"{logical_name} 상태 코드",
                        "attribute_name": f"{logical_name} 상태 코드",
                        "physical_name": f"{base_name}_stts_cd",
                        "column_name": f"{base_name}_stts_cd",
                        "data_type": "VARCHAR(20)",
                        "nullable": True,
                        "constraints": [],
                        "description": f"{logical_name} 처리 상태 코드",
                    },
                    {
                        "column_id": f"COL-{index + 1:03d}-005",
                        "logical_name": "사용 여부",
                        "attribute_name": "사용 여부",
                        "physical_name": "use_yn",
                        "column_name": "use_yn",
                        "data_type": "CHAR(1)",
                        "nullable": False,
                        "constraints": [],
                        "description": "사용 여부",
                    },
                    {
                        "column_id": f"COL-{index + 1:03d}-006",
                        "logical_name": "등록 일시",
                        "attribute_name": "등록 일시",
                        "physical_name": "reg_dt",
                        "column_name": "reg_dt",
                        "data_type": "DATETIME",
                        "nullable": False,
                        "constraints": [],
                        "description": "데이터 등록 일시",
                    },
                    {
                        "column_id": f"COL-{index + 1:03d}-007",
                        "logical_name": "수정 일시",
                        "attribute_name": "수정 일시",
                        "physical_name": "mdfcn_dt",
                        "column_name": "mdfcn_dt",
                        "data_type": "DATETIME",
                        "nullable": True,
                        "constraints": [],
                        "description": "데이터 수정 일시",
                    },
                ],
            }
        )
    return tables


def normalize_erd_tables(items: list[Any]) -> list[dict[str, Any]]:
    raw_tables = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        raw_physical_name = _raw_table_physical_name(item)
        logical_name = _normalize_entity_logical_name(item, index, raw_physical_name)
        raw_physical_name = _raw_table_physical_name(item)
        physical_name = _standard_table_name(raw_physical_name, logical_name)
        columns = item.get("columns") if isinstance(item.get("columns"), list) else []
        if not columns:
            columns = build_erd_tables([{"logical_name": logical_name}])[0]["columns"]
        raw_tables.append(
            {
                **item,
                "table_id": str(item.get("table_id") or f"TABLE-{index + 1:03d}"),
                "entity_id": str(item.get("entity_id") or f"ENT-{index + 1:03d}"),
                "related_class_id": str(item.get("related_class_id") or item.get("class_id") or ""),
                "related_class_name": str(item.get("related_class_name") or item.get("class_name") or ""),
                "logical_name": logical_name,
                "entity_name": logical_name,
                "physical_name": physical_name,
                "table_name": physical_name,
                "description": _table_description(logical_name),
                "entity_description": _table_description(logical_name),
                "table_description": _table_description(logical_name),
                "columns": _ensure_minimum_columns(
                    [_normalize_erd_column(column, index, col_index, logical_name) for col_index, column in enumerate(columns)],
                    index,
                    logical_name,
                    physical_name,
                ),
            }
        )
    return _dedupe_table_and_column_names(_merge_duplicate_tables(raw_tables))


def _normalize_entity_logical_name(item: dict[str, Any], index: int, raw_physical_name: str) -> str:
    for key in ("entity_name", "logical_name", "table_logical_name", "table_korean_name"):
        value = str(item.get(key) or "").strip()
        if value and not _looks_like_table_identifier(value) and not _is_generic_entity_name(value):
            return _short_text(value, 40)
    return ""


def _raw_table_physical_name(item: dict[str, Any]) -> str:
    table_id = str(item.get("table_id") or "").strip()
    physical = str(item.get("physical_name") or "").strip()
    table = str(item.get("table_name") or "").strip()
    if table_id.lower().startswith("tbl_") and _looks_like_physical_name(table_id):
        return table_id
    if physical in {"tbl_entity", "tbl_table", "tbl_data", "tbl_info", "tbl_object", "tbl_item"} and _looks_like_physical_name(table):
        return table
    if _looks_like_physical_name(physical):
        return physical
    if _looks_like_physical_name(table):
        return table
    return physical or table


def build_db_design(tables: list[dict[str, Any]]) -> dict[str, Any]:
    db_tables = []
    for table in tables:
        physical_table_name = table["physical_name"]
        logical_table_name = table.get("logical_name") or physical_table_name
        db_tables.append(
            {
                "table_id": physical_table_name,
                "table_name": physical_table_name,
                "table_logical_name": logical_table_name,
                "database_name": "업무 DB",
                "tablespace_name": tablespace_name(physical_table_name),
                "trigger_config": "해당 없음",
                "table_description": table.get("description") or table["logical_name"],
                "initial_count": "0",
                "daily_growth": "산정 필요",
                "retention_period": "업무 기준에 따름",
                "max_count": "산정 필요",
                "capacity": "산정 필요",
                "note": "",
                "columns": [
                    {
                        "column_name": column["physical_name"],
                        "column_id": column.get("standard_column_id") or column["physical_name"],
                        "column_logical_name": db_column_logical_name(
                            column.get("attribute_name")
                            or column.get("logical_name")
                            or column.get("column_logical_name"),
                            column["physical_name"],
                            physical_table_name,
                            "PK" in column.get("constraints", []),
                        ),
                        "data_type": column.get("data_type") or "VARCHAR(255)",
                        "type_and_length": format_type_and_length(
                            column.get("data_type") or "VARCHAR(255)",
                            column.get("length"),
                        ),
                        "nullable": column.get("nullable", True),
                        "not_null": "Y" if not bool(column.get("nullable", True)) else "",
                        "pk": "Y" if "PK" in column.get("constraints", []) else "",
                        "fk": "Y" if "FK" in column.get("constraints", []) else "",
                        "idx": "Y" if any(item in column.get("constraints", []) for item in ("PK", "FK", "INDEX", "IDX")) else "",
                        "default": column.get("default"),
                        "description": column.get("logical_name") or column["physical_name"],
                        "constraint": _column_constraint_text(column),
                        "constraints": column.get("constraints", []),
                    }
                    for column in table.get("columns", [])
                ],
                "constraints": _constraints(table),
                "indexes": [],
            }
        )
    return {
        "database_id": "DB-001",
        "database_name": "업무 DB",
        "storage_group": "업무 기준에 따름",
        "bufferpool": "업무 기준에 따름",
        "index_bufferpool": "업무 기준에 따름",
        "tables": db_tables,
    }


def normalize_db_design(items: list[Any]) -> dict[str, Any]:
    erd_tables = normalize_erd_tables(items)
    return build_db_design(erd_tables)


def apply_public_standard_results(
    tables: list[dict[str, Any]],
    rag_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    standards_by_table = {
        str(item.get("table_id")): _parse_standard_results(item.get("normalized_results") or [])
        for item in rag_results
        if isinstance(item, dict)
    }
    updated = []
    for table in tables:
        source = deepcopy(table)
        standards = standards_by_table.get(str(source.get("table_id")), [])
        source["columns"] = [
            _apply_column_standard(source, column, standards)
            for column in source.get("columns", [])
            if isinstance(column, dict)
        ]
        updated.append(source)
    return normalize_erd_tables(updated)


def _normalize_erd_column(column: Any, table_index: int, column_index: int, logical_name: str) -> dict[str, Any]:
    source = deepcopy(column) if isinstance(column, dict) else {}
    raw_name = str(source.get("physical_name") or source.get("column_name") or "")
    logical_column_name = str(
        source.get("attribute_name")
        or source.get("logical_name")
        or source.get("column_logical_name")
        or source.get("description")
        or f"{logical_name} 컬럼"
    )
    data_type, length = split_data_type(str(source.get("data_type") or source.get("type_and_length") or "BIGINT"))
    raw_constraints = source.get("constraints")
    explicit_pk = _has_constraint(raw_constraints, "PK") or _truthy(source.get("pk")) or _truthy(source.get("is_pk"))
    force_pk = explicit_pk or (column_index == 0 and not raw_name and not raw_constraints)
    physical_name = _standard_column_name(raw_name, logical_column_name, logical_name, force_pk)
    constraints = _normalize_column_constraints(source.get("constraints"), source.get("constraint"), force_pk)
    default_value, inferred_constraints = _infer_default_and_constraints(
        physical_name=physical_name,
        logical_name=logical_column_name,
        data_type=data_type,
        constraints=constraints,
        default_value=source.get("default"),
        table_physical_name="",
    )
    return {
        **source,
        "column_id": str(source.get("column_id") or f"COL-{table_index + 1:03d}-{column_index + 1:03d}"),
        "logical_name": logical_column_name,
        "attribute_name": logical_column_name,
        "physical_name": physical_name,
        "column_name": physical_name,
        "data_type": data_type,
        "length": str(source.get("length") or length),
        "nullable": source.get("nullable", not force_pk),
        "constraints": list(dict.fromkeys([*constraints, *inferred_constraints])),
        "default": default_value,
        "description": _summary_text(source.get("description") or logical_column_name, 60),
    }


def _standard_table_name(raw_name: str, logical_name: str) -> str:
    source = raw_name or table_name(logical_name)
    standardized = standardize_name(source, fallback="entity")
    if standardized in {"tbl", "tbl_entity", "tbl_table", "tbl_data", "tbl_info", "tbl_object", "tbl_item"}:
        standardized = standardize_name(logical_name, fallback="entity")
    return standardized if standardized.startswith("tbl_") else f"tbl_{standardized}"


def _standard_column_name(
    raw_name: str,
    logical_column_name: str,
    table_logical_name: str,
    is_pk: bool,
) -> str:
    if is_pk:
        candidate = raw_name or primary_key_name(table_logical_name)
    else:
        candidate = raw_name or logical_column_name
    standardized = standardize_name(candidate, fallback="column")
    if is_pk and not standardized.endswith(("_sn", "_id")):
        return primary_key_name(table_logical_name)
    return standardized.removeprefix("tbl_")


def _dedupe_table_and_column_names(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for table_index, table in enumerate(tables):
        table["table_id"] = f"TABLE-{table_index + 1:03d}"
        table["entity_id"] = f"ENT-{table_index + 1:03d}"
        seen_physical_names: set[str] = set()
        unique_columns = []
        for column in table.get("columns", []):
            base_column = str(column.get("physical_name") or "").strip().lower()
            if not base_column or base_column in seen_physical_names:
                continue
            seen_physical_names.add(base_column)
            unique_columns.append(column)
        for column_index, column in enumerate(unique_columns, start=1):
            column["column_id"] = f"COL-{table_index + 1:03d}-{column_index:03d}"
        table["columns"] = unique_columns
    return tables


def _short_text(value: Any, max_length: int) -> str:
    text = str(value or "").replace("\n", " ").strip()
    return text if len(text) <= max_length else text[:max_length].rstrip()


def _summary_text(value: Any, max_length: int) -> str:
    text = str(value or "").replace("\n", " ").strip()
    for marker in ("다.", ".", "요.", "임."):
        if marker in text:
            candidate = text.split(marker, 1)[0].strip() + marker
            return _short_text(candidate, max_length)
    return _short_text(text, max_length)


def _table_description(logical_name: Any) -> str:
    subject = _description_subject(logical_name)
    if not subject:
        subject = "업무"
    if subject.endswith("정보"):
        return f"{subject}를 관리하는 테이블입니다."
    if subject.endswith("관리"):
        return f"{subject} 업무 정보를 관리하는 테이블입니다."
    return f"{subject} 정보를 관리하는 테이블입니다."


def _description_subject(value: Any) -> str:
    text = str(value or "").replace("\n", " ").replace("\r", " ").strip()
    text = re.sub(r"[\[\]{}()<>※★*#|`\"'·•:;]", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -_/.,")
    text = re.sub(r"(테이블|엔티티)$", "", text).strip()
    return _short_text(text, 40)


def _is_generic_entity_name(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text in {"엔티티", "entity", "table", "테이블", "데이터", "정보", "객체", "항목", "관리", "업무"}


def _looks_like_physical_name(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return bool(re.fullmatch(r"(tbl_)?[A-Za-z][A-Za-z0-9_]*", text) or re.fullmatch(r"TABLE-\d+", text, re.IGNORECASE))


def _looks_like_table_identifier(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text.lower().startswith("tbl_") or re.fullmatch(r"TABLE-\d+", text, re.IGNORECASE))


def _merge_duplicate_tables(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for table in tables:
        key = table["physical_name"]
        if key not in merged:
            merged[key] = table
            order.append(key)
            continue
        target = merged[key]
        target["source_requirement_ids"] = list(
            dict.fromkeys([*target.get("source_requirement_ids", []), *table.get("source_requirement_ids", [])])
        )
        target["columns"] = [*target.get("columns", []), *table.get("columns", [])]
        target["description"] = _table_description(target.get("logical_name"))
        target["table_description"] = target["description"]
    return [merged[key] for key in order]


def _ensure_minimum_columns(
    columns: list[dict[str, Any]],
    table_index: int,
    logical_name: str,
    physical_name: str,
) -> list[dict[str, Any]]:
    base_name = physical_name.removeprefix("tbl_")
    existing = {column["physical_name"] for column in columns}
    required = [
        (f"{base_name}_nm", f"{logical_name} 명", "VARCHAR(200)", False, f"{logical_name} 명칭"),
        (f"{base_name}_cn", f"{logical_name} 내용", "TEXT", True, f"{logical_name} 상세 내용"),
        (f"{base_name}_stts_cd", f"{logical_name} 상태 코드", "VARCHAR(20)", True, f"{logical_name} 처리 상태 코드"),
        ("use_yn", "사용 여부", "CHAR(1)", False, "사용 여부"),
        ("reg_dt", "등록 일시", "DATETIME", False, "데이터 등록 일시"),
        ("mdfcn_dt", "수정 일시", "DATETIME", True, "데이터 수정 일시"),
    ]
    for physical, logical, data_type, nullable, description in required:
        if len(columns) >= 6:
            break
        if physical in existing:
            continue
        existing.add(physical)
        columns.append(
            {
                "column_id": f"COL-{table_index + 1:03d}-{len(columns) + 1:03d}",
                "logical_name": logical,
                "attribute_name": logical,
                "physical_name": physical,
                "column_name": physical,
                "data_type": data_type,
                "nullable": nullable,
                "constraints": [],
                "description": description,
            }
        )
    return columns


def _constraints(table: dict[str, Any]) -> list[dict[str, Any]]:
    constraints = []
    for column in table.get("columns", []):
        if "PK" in column.get("constraints", []):
            constraints.append({"type": "PK", "columns": [column["physical_name"]]})
    return constraints


def _column_constraint_text(column: dict[str, Any]) -> str:
    constraints = column.get("constraints") if isinstance(column.get("constraints"), list) else []
    return "; ".join(
        str(item)
        for item in constraints
        if str(item).upper() not in {"PK", "FK", "INDEX", "IDX", "NOT NULL"}
    )


def split_data_type(value: Any) -> tuple[str, str]:
    text = str(value or "").strip()
    match = re.match(r"^([A-Za-z가-힣_]+)\s*\(([^)]+)\)$", text)
    if match:
        return _normalize_type_name(match.group(1)), match.group(2).strip()
    return _normalize_type_name(text or "VARCHAR"), ""


def format_type_and_length(data_type: Any, length: Any = "") -> str:
    type_name, embedded_length = split_data_type(data_type)
    selected_length = str(length or embedded_length or "").strip()
    if selected_length and type_name not in {"TEXT", "DATETIME"}:
        return f"{type_name}({selected_length})"
    return type_name


def _normalize_type_name(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {
        "VARCHAR2": "VARCHAR",
        "VARCHAR": "VARCHAR",
        "CHARACTER": "CHAR",
        "NUMBER": "NUMERIC",
        "INTEGER": "INTEGER",
        "INT": "INTEGER",
        "DATETIME": "DATETIME",
        "TIMESTAMP": "DATETIME",
        "TEXT": "TEXT",
    }
    return aliases.get(text, text or "VARCHAR")


def _apply_column_standard(
    table: dict[str, Any],
    column: dict[str, Any],
    standards: list[dict[str, str]],
) -> dict[str, Any]:
    is_pk = "PK" in column.get("constraints", [])
    physical = str(column.get("physical_name") or column.get("column_name") or "")
    fallback_logical = display_column_name(column.get("logical_name"), physical, table.get("physical_name"), is_pk)
    standard = _best_standard_match(fallback_logical, column.get("logical_name"), physical, standards)
    if not standard:
        data_type, length = split_data_type(column.get("data_type"))
        default_value, inferred_constraints = _infer_default_and_constraints(
            physical_name=physical,
            logical_name=fallback_logical,
            data_type=data_type,
            constraints=column.get("constraints", []),
            default_value=column.get("default"),
            table_physical_name=table.get("physical_name"),
        )
        return {
            **column,
            "logical_name": fallback_logical,
            "data_type": data_type,
            "length": str(column.get("length") or length),
            "synonym": _clean_optional_text(column.get("synonym")),
            "standard_source": column.get("standard_source"),
            "default": default_value,
            "constraints": list(dict.fromkeys([*(column.get("constraints") or []), *inferred_constraints])),
        }

    data_type, length = _standard_type_and_length(standard, column)
    physical_name = _standard_physical_name(standard.get("abbr"), physical)
    default_value, inferred_constraints = _infer_default_and_constraints(
        physical_name=physical_name,
        logical_name=standard.get("term") or fallback_logical,
        data_type=data_type,
        constraints=column.get("constraints", []),
        default_value=column.get("default"),
        table_physical_name=table.get("physical_name"),
    )
    return {
        **column,
        "logical_name": standard.get("term") or fallback_logical,
        "physical_name": physical_name,
        "data_type": data_type,
        "length": length,
        "synonym": _clean_optional_text(standard.get("synonym") or column.get("synonym")),
        "default": default_value,
        "constraints": list(dict.fromkeys([*(column.get("constraints") or []), *inferred_constraints])),
        "standard_source": {
            "doc_type": standard.get("doc_type"),
            "title": standard.get("title"),
            "term": standard.get("term"),
            "abbr": standard.get("abbr"),
            "domain_name": standard.get("domain_name"),
        },
    }


def _standard_physical_name(abbr: Any, fallback: str) -> str:
    value = str(abbr or "").strip()
    if not value:
        return fallback
    return standardize_name(value, fallback=fallback or "column")


def _standard_type_and_length(standard: dict[str, str], column: dict[str, Any]) -> tuple[str, str]:
    domain = standard.get("domain_name", "")
    data_type = standard.get("data_type", "")
    length = standard.get("length", "")
    if not data_type:
        data_type, inferred_length = _infer_type_from_domain(domain)
        length = length or inferred_length
    if not data_type:
        data_type, inferred_length = split_data_type(column.get("data_type"))
        length = length or str(column.get("length") or inferred_length)
    return data_type, length


def _infer_type_from_domain(domain_name: str) -> tuple[str, str]:
    text = str(domain_name or "").upper()
    if not text:
        return "", ""
    match = re.search(r"([A-Z가-힣]+)(\d+)", text)
    token = match.group(1) if match else text
    length = match.group(2) if match else ""
    if token.startswith(("연월일시", "일시")):
        return "DATETIME", length or "14"
    if token.startswith(("연월일", "일자", "날짜")):
        return "CHAR", length or "8"
    if token.startswith(("여부",)):
        return "CHAR", length or "1"
    if token.startswith(("코드",)):
        return "CHAR", length or "20"
    if token.startswith(("번호",)):
        return "VARCHAR", length or "20"
    if token.startswith(("명", "내용", "문자", "전화번호", "주소")):
        return "VARCHAR", length
    if token.startswith(("수", "금액", "율", "건수")):
        return "NUMERIC", length
    return "", length


def _best_standard_match(
    display_name: Any,
    logical_name: Any,
    physical_name: Any,
    standards: list[dict[str, str]],
) -> dict[str, str] | None:
    candidates = [_clean_match_text(display_name), _clean_match_text(logical_name)]
    physical = str(physical_name or "").lower()
    best = None
    best_score = 0
    for standard in standards:
        term = _clean_match_text(standard.get("term"))
        abbr = str(standard.get("abbr") or "").lower()
        if not term and not abbr:
            continue
        score = 0
        for candidate in candidates:
            if not candidate:
                continue
            if candidate == term:
                score = max(score, 100)
            elif candidate in term or term in candidate:
                score = max(score, 70)
        if abbr and abbr.lower() in physical:
            score = max(score, 80)
        if score > best_score:
            best = standard
            best_score = score
    return best if best_score >= 70 else None


def _clean_match_text(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"(일련번호|고유식별자)$", "ID", text)
    if text in {"번호", "아이디"}:
        return "ID"
    return text


def _parse_standard_results(results: list[Any]) -> list[dict[str, str]]:
    standards = []
    for item in results:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata") or {}
        content = str(item.get("content") or "")
        doc_type = str(metadata.get("doc_type") or "")
        parsed = {
            "doc_type": _clean_optional_text(doc_type),
            "title": _clean_optional_text(metadata.get("title") or item.get("title")),
            "term": _clean_optional_text(_field(content, "공통표준용어명") or _field(content, "공통표준단어명")),
            "abbr": _clean_optional_text(_field(content, "공통표준용어영문약어명") or _field(content, "공통표준단어영문약어명")),
            "domain_name": _clean_optional_text(_field(content, "공통표준도메인명") or _field(content, "공통표준도메인분류명")),
            "data_type": _clean_optional_text(_field(content, "데이터타입")),
            "storage_format": _clean_optional_text(_field(content, "저장 형식")),
            "synonym": _clean_optional_text(_field(content, "용어 이음동의어 목록") or _field(content, "이음동의어 목록")),
        }
        parsed["length"] = _length_from_storage_format(parsed["storage_format"])
        if parsed["term"] or parsed["abbr"] or parsed["domain_name"]:
            standards.append(parsed)
    return standards


def _field(content: str, label: str) -> str:
    match = re.search(rf"{re.escape(label)}\s*:\s*([^|]+)", content)
    return match.group(1).strip() if match else ""


def _clean_optional_text(value: Any) -> str:
    text = str(value or "").strip()
    if text in {"", "-", "–", "—", "N/A", "n/a", "없음", "해당 없음", "null", "None"}:
        return ""
    return text


def _length_from_storage_format(value: str) -> str:
    text = str(value or "")
    match = re.search(r"(\d+)\s*자리", text)
    if match:
        return match.group(1)
    if "YYYYMMDDHH24MISS" in text:
        return "14"
    if "YYYYMMDD" in text:
        return "8"
    return ""


def display_column_name(
    logical_name: Any,
    physical_name: Any,
    table_name_value: Any,
    is_pk: bool = False,
) -> str:
    physical = str(physical_name or "").strip()
    table_base = str(table_name_value or "").lower().removeprefix("tbl_")
    normalized = physical.lower()
    if table_base and normalized.startswith(f"{table_base}_"):
        normalized = normalized[len(table_base) + 1 :]
    normalized = normalized.strip("_")

    if normalized in {"sn", "id", "no", "num"} or normalized.endswith(("_sn", "_id")):
        return "ID"

    mapped = _COLUMN_DISPLAY_MAP.get(normalized)
    if mapped:
        return mapped

    text = _clean_display_text(logical_name)
    if _is_bad_display_text(text):
        text = ""
    if text and len(text) <= 12:
        return text
    if text:
        for suffix in ("일련번호", "번호", "아이디", "명", "이름", "내용", "상태 코드", "상태", "코드", "일시", "일자", "비밀번호"):
            if text.endswith(suffix):
                return "ID" if suffix in {"일련번호", "번호", "아이디"} else suffix
        extracted = _extract_display_token(text)
        if extracted:
            return extracted

    if normalized:
        inferred = _display_from_physical_name(normalized)
        if inferred:
            return inferred
        return normalized.upper() if len(normalized) <= 4 else normalized
    return text or "컬럼"


def db_column_logical_name(
    logical_name: Any,
    physical_name: Any,
    table_name_value: Any,
    is_pk: bool = False,
) -> str:
    """DB 컬럼명에는 참조 ERD 속성명을 보존하고, 누락된 경우에만 추론합니다."""

    text = re.sub(r"\s+", " ", str(logical_name or "").replace("\n", " ")).strip()
    if text and text not in {"-", "–", "—", "N/A", "없음"}:
        return text
    return display_column_name(logical_name, physical_name, table_name_value, is_pk)


def _clean_display_text(value: Any) -> str:
    text = str(value or "").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    text = text.strip(" -_/.,")
    text = re.sub(r"(고유\s*)?(식별자|관리|정보)$", "", text).strip()
    return text


def _is_bad_display_text(text: str) -> bool:
    if not text or text in {"-", "–", "—", "N/A", "없음"}:
        return True
    if len(text) > 24:
        return True
    bad_phrases = ("정보를 관리", "테이블입니다", "관리하는 테이블", "상세 내용", "기본사항")
    return any(phrase in text for phrase in bad_phrases)


def _extract_display_token(text: str) -> str:
    keywords = [
        "상태코드",
        "상태 코드",
        "등록일시",
        "등록 일시",
        "생성일시",
        "생성 일시",
        "수정일시",
        "수정 일시",
        "사용여부",
        "사용 여부",
        "삭제여부",
        "삭제 여부",
        "이메일",
        "비밀번호",
        "URL",
        "내용",
        "설명",
        "명",
    ]
    compact = text.replace(" ", "")
    for keyword in keywords:
        if keyword.replace(" ", "") in compact:
            return keyword.replace(" ", "")
    return ""


def _display_from_physical_name(normalized: str) -> str:
    if not normalized:
        return ""
    mapped = _COLUMN_DISPLAY_MAP.get(normalized)
    if mapped:
        return mapped
    suffix_map = {
        "_nm": "명",
        "_name": "명",
        "_cn": "내용",
        "_content": "내용",
        "_desc": "설명",
        "_description": "설명",
        "_stts_cd": "상태코드",
        "_status_cd": "상태코드",
        "_status": "상태",
        "_cd": "코드",
        "_code": "코드",
        "_dt": "일시",
        "_date": "일자",
        "_ymd": "일자",
        "_yn": "여부",
        "_url": "URL",
    }
    for suffix, label in suffix_map.items():
        if normalized.endswith(suffix):
            return label
    if "email" in normalized:
        return "이메일"
    if "password" in normalized or "pswd" in normalized:
        return "비밀번호"
    tokens = [token for token in normalized.split("_") if token]
    if tokens:
        last = tokens[-1]
        return last.upper() if len(last) <= 4 else last
    return ""


_COLUMN_DISPLAY_MAP = {
    "nm": "명",
    "name": "명",
    "cn": "내용",
    "content": "내용",
    "desc": "설명",
    "description": "설명",
    "stts_cd": "상태코드",
    "status_cd": "상태코드",
    "status": "상태",
    "cd": "코드",
    "code": "코드",
    "use_yn": "사용여부",
    "del_yn": "삭제여부",
    "reg_dt": "등록일시",
    "crt_dt": "등록일시",
    "created_dt": "등록일시",
    "mdfcn_dt": "수정일시",
    "upd_dt": "수정일시",
    "updated_dt": "수정일시",
    "pswd": "비밀번호",
    "pwd": "비밀번호",
    "password": "비밀번호",
    "email": "이메일",
    "tel": "전화번호",
    "phone": "전화번호",
    "addr": "주소",
    "address": "주소",
    "url": "URL",
}


def _normalize_column_constraints(raw_constraints: Any, raw_constraint: Any, is_pk: bool) -> list[str]:
    values: list[str] = ["PK"] if is_pk else []
    candidates: list[Any] = []
    if isinstance(raw_constraints, list):
        candidates.extend(raw_constraints)
    elif raw_constraints:
        candidates.append(raw_constraints)
    if raw_constraint:
        candidates.append(raw_constraint)
    for candidate in candidates:
        text = str(candidate).strip()
        if not text:
            continue
        upper = text.upper()
        if upper in {"PK", "PRIMARY KEY"}:
            if "PK" not in values:
                values.append("PK")
            continue
        if upper in {"FK", "FOREIGN KEY"}:
            if "FK" not in values:
                values.append("FK")
            continue
        if _looks_like_db_constraint(text):
            values.append(text)
            continue
        if _looks_like_business_constraint(text):
            values.append(text)
    return list(dict.fromkeys(values))


def _infer_default_and_constraints(
    *,
    physical_name: Any,
    logical_name: Any,
    data_type: Any,
    constraints: Any,
    default_value: Any,
    table_physical_name: Any,
) -> tuple[str, list[str]]:
    name = str(physical_name or "").lower()
    logical = str(logical_name or "")
    dtype = str(data_type or "").upper()
    existing = constraints if isinstance(constraints, list) else []
    existing_upper = {str(item).upper() for item in existing}
    default_text = str(default_value or "").strip()
    inferred: list[str] = []

    is_pk = "PK" in existing_upper
    is_fk = "FK" in existing_upper or (
        name.endswith(("_id", "_sn"))
        and not is_pk
        and bool(table_physical_name)
        and not _same_table_identifier(name, table_physical_name)
    )

    if not default_text:
        if name in {"use_yn", "del_yn"} or logical.endswith("여부"):
            default_text = "Y" if name == "use_yn" or "사용" in logical else "N"
        elif name in {"created_at", "created_dt", "crt_dt", "reg_dt"} or "생성 일시" in logical or "등록 일시" in logical:
            default_text = "CURRENT_TIMESTAMP"
        elif name in {"updated_at", "updated_dt", "upd_dt", "mdfcn_dt"} or "수정 일시" in logical:
            default_text = "CURRENT_TIMESTAMP"
        elif name.endswith("_type") or "유형" in logical:
            default_text = _default_for_type_column(name, logical)
        elif name.endswith(("_stts_cd", "_status")) or "상태" in logical:
            default_text = _default_for_status_column(name, logical)
        elif name.endswith("_role_cd") or "역할" in logical:
            default_text = "USER"
    if is_pk and "AUTO_INCREMENT" not in existing_upper:
        inferred.append("AUTO_INCREMENT")

    return default_text, [
        item
        for item in inferred
        if item and item.upper() not in existing_upper
    ]


def _same_table_identifier(column_name: str, table_physical_name: Any) -> bool:
    table_base = str(table_physical_name or "").lower().removeprefix("tbl_")
    return column_name in {f"{table_base}_id", f"{table_base}_sn"}


def _guess_fk_table_name(column_name: str) -> str:
    base = column_name.removesuffix("_id").removesuffix("_sn")
    return f"tbl_{base}" if base else ""


def _default_for_type_column(name: str, logical: str) -> str:
    if "provider" in name or "제공자" in logical:
        return "COMMERCIAL"
    if "model" in name or "모델" in logical:
        return "LLM"
    return ""


def _allowed_values_for_type_column(name: str, logical: str) -> str:
    if "provider" in name or "제공자" in logical:
        return "COMMERCIAL/ON_PREMISE"
    if "model" in name or "모델" in logical:
        return "LLM/EMBEDDING/RERANKER"
    return ""


def _default_for_status_column(name: str, logical: str) -> str:
    if "approval" in name or "승인" in logical:
        return "PENDING"
    if "process" in name or "처리" in logical:
        return "READY"
    return "ACTIVE"


def _allowed_values_for_status_column(name: str, logical: str) -> str:
    if "approval" in name or "승인" in logical:
        return "PENDING/APPROVED/REJECTED"
    if "process" in name or "처리" in logical:
        return "READY/RUNNING/DONE/FAILED"
    return "ACTIVE/INACTIVE"


def _has_constraint(value: Any, expected: str) -> bool:
    expected = expected.upper()
    if isinstance(value, list):
        return any(str(item).upper() in {expected, "PRIMARY KEY" if expected == "PK" else expected} for item in value)
    return str(value or "").upper() in {expected, "PRIMARY KEY" if expected == "PK" else expected}


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().upper() in {"Y", "YES", "TRUE", "1", "PK"}
    return bool(value)


def _looks_like_business_constraint(text: str) -> bool:
    keywords = {
        "마스킹",
        "암호",
        "해시",
        "권한",
        "접근",
        "보관",
        "파기",
        "개인정보",
        "필수",
        "유일",
        "중복",
        "최소",
        "최대",
        "이내",
        "초",
        "분",
        "허용",
        "금지",
        "검증",
        "제한",
        "정책",
        "감사",
        "로그",
        "백업",
    }
    return any(keyword in text for keyword in keywords)


def _looks_like_db_constraint(text: str) -> bool:
    upper = text.upper()
    if upper in {"AUTO_INCREMENT", "UNIQUE", "Y/N", "URL 형식"}:
        return True
    if upper.startswith("FK "):
        return True
    if "/" in text and len(text) <= 80:
        return True
    return False
