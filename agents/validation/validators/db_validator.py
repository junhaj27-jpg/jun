# DB 설계서의 테이블과 컬럼 구조를 검증합니다.

from typing import Any

from agents.data_structure_design.processors.table_builder import (
    display_column_name,
    format_type_and_length,
    normalize_erd_tables,
)
from agents.validation.schemas import first_list, is_empty, make_check, missing_fields, missing_keys
from workflow.state import WorkflowState


TARGET = "data_structure_design_agent"


def validate(state: WorkflowState) -> list[dict[str, Any]]:
    document = state.get("agent_outputs", {}).get(TARGET, {}).get("db_design_json")
    tables = first_list(document, "tables", "table_json_list")
    checks = [
        make_check("DB_OUTPUT_001", "DB 설계 출력 존재 검증", not is_empty(document), failure_type="DB_OUTPUT_MISSING", message="db_design_json이 없습니다.", target_agent=TARGET)
    ]
    if not tables:
        checks.append(make_check("DB_SCHEMA_001", "DB 설계 Schema 검증", False, failure_type="DB_SCHEMA_ERROR", message="DB 테이블 목록이 없거나 구조가 올바르지 않습니다.", target_agent=TARGET))
        return checks

    table_missing, column_missing, type_missing, constraint_invalid, index_invalid, ddl_invalid = [], [], [], [], [], []
    for index, table in enumerate(tables):
        scope = str(table.get("table_name") or index) if isinstance(table, dict) else str(index)
        if not isinstance(table, dict) or missing_fields(table, ["table_name", "table_description", "columns"]) or missing_keys(table, ["constraints", "indexes"]):
            table_missing.append(scope)
            continue
        columns = table["columns"] if isinstance(table["columns"], list) else []
        if not columns or any(not isinstance(column, dict) or missing_fields(column, ["column_name", "data_type", "description"]) or missing_keys(column, ["nullable", "default"]) for column in columns):
            column_missing.append(scope)
        if any(is_empty(column.get("data_type")) for column in columns if isinstance(column, dict)):
            type_missing.append(scope)
        constraints = table.get("constraints")
        indexes = table.get("indexes")
        column_names = {str(column.get("column_name")) for column in columns if isinstance(column, dict)}
        if not isinstance(constraints, list) or _invalid_column_refs(constraints, column_names, "columns"):
            constraint_invalid.append(scope)
        if not isinstance(indexes, list) or _invalid_column_refs(indexes, column_names, "columns"):
            index_invalid.append(scope)
        if any(" " in str(column.get("column_name") or "") for column in columns if isinstance(column, dict)):
            ddl_invalid.append(scope)
    reference_tables, reference_columns = _reference_names(state)
    reference_specs = _reference_column_specs(state)
    design_tables = {str(table.get("table_name")) for table in tables if isinstance(table, dict)}
    design_columns = {
        (str(table.get("table_name")), str(column.get("column_name")))
        for table in tables if isinstance(table, dict)
        for column in table.get("columns", []) if isinstance(column, dict)
    }
    design_specs = _design_column_specs(tables)
    missing_tables = sorted(reference_tables - design_tables)
    missing_reference_columns = sorted(f"{table}.{column}" for table, column in reference_columns - design_columns)
    comparable_specs = {
        key: spec
        for key, spec in reference_specs.items()
        if key in design_specs
    }
    name_mismatches = _compare_column_spec(comparable_specs, design_specs, "column_logical_name")
    type_mismatches = _compare_column_spec(comparable_specs, design_specs, "type_and_length")
    not_null_mismatches = _compare_column_spec(comparable_specs, design_specs, "not_null")
    pk_mismatches = _compare_column_spec(comparable_specs, design_specs, "pk")
    fk_mismatches = _compare_column_spec(comparable_specs, design_specs, "fk")
    idx_mismatches = _compare_column_spec(comparable_specs, design_specs, "idx")
    default_mismatches = _compare_column_spec(comparable_specs, design_specs, "default")
    constraint_mismatches = _compare_column_spec(comparable_specs, design_specs, "constraint")
    checks.extend(
        [
            make_check("DB_SCHEMA_001", "DB 테이블 필수 필드 검증", not table_missing, failure_type="DB_SCHEMA_ERROR", message="테이블 필수 필드가 누락되었습니다.", target_agent=TARGET, target_scope=table_missing),
            make_check("DB_COLUMN_001", "DB 컬럼 검증", not column_missing, failure_type="DB_COLUMN_MISSING", message="컬럼 또는 컬럼 필수 필드가 누락되었습니다.", target_agent=TARGET, target_scope=column_missing),
            make_check("DB_TYPE_001", "데이터 타입 검증", not type_missing, failure_type="DB_DATA_TYPE_MISSING", message="데이터 타입이 누락된 컬럼이 있습니다.", target_agent=TARGET, target_scope=type_missing),
            make_check("DB_CONSTRAINT_001", "제약조건 구조 검증", not constraint_invalid, failure_type="DB_CONSTRAINT_INVALID", message="제약조건 구조가 올바르지 않습니다.", target_agent=TARGET, target_scope=constraint_invalid),
            make_check("DB_INDEX_001", "인덱스 구조 검증", not index_invalid, failure_type="DB_INDEX_INVALID", message="인덱스 구조가 올바르지 않습니다.", target_agent=TARGET, target_scope=index_invalid, severity="MEDIUM"),
            make_check("DB_REFERENCE_001", "참조 ERD 테이블 반영 검증", not missing_tables, failure_type="DB_TABLE_MISSING", message="참조 ERD 테이블이 DB 설계에 누락되었습니다.", target_agent=TARGET, target_scope=missing_tables),
            make_check("DB_REFERENCE_002", "참조 ERD 컬럼 반영 검증", not missing_reference_columns, failure_type="DB_COLUMN_MISSING", message="참조 ERD 컬럼이 DB 설계에 누락되었습니다.", target_agent=TARGET, target_scope=missing_reference_columns),
            make_check("DB_REFERENCE_003", "참조 ERD 속성명-DB 컬럼명 일치 검증", not name_mismatches, failure_type="DB_COLUMN_MISSING", message="DB 컬럼명이 참조 ERD 속성명과 다릅니다.", target_agent=TARGET, target_scope=name_mismatches),
            make_check("DB_REFERENCE_004", "참조 ERD 타입 및 길이 일치 검증", not type_mismatches, failure_type="DB_DATA_TYPE_MISSING", message="DB 타입 및 길이가 참조 ERD와 다릅니다.", target_agent=TARGET, target_scope=type_mismatches),
            make_check("DB_REFERENCE_005", "참조 ERD Not Null 일치 검증", not not_null_mismatches, failure_type="DB_CONSTRAINT_INVALID", message="DB Not Null 값이 참조 ERD와 다릅니다.", target_agent=TARGET, target_scope=not_null_mismatches),
            make_check("DB_REFERENCE_006", "참조 ERD PK/FK/IDX 일치 검증", not (pk_mismatches or fk_mismatches or idx_mismatches), failure_type="DB_CONSTRAINT_INVALID", message="DB PK/FK/IDX 값이 참조 ERD와 다릅니다.", target_agent=TARGET, target_scope=pk_mismatches + fk_mismatches + idx_mismatches),
            make_check("DB_REFERENCE_007", "참조 ERD 기본값 일치 검증", not default_mismatches, failure_type="DB_CONSTRAINT_INVALID", message="DB 기본값이 참조 ERD와 다릅니다.", target_agent=TARGET, target_scope=default_mismatches),
            make_check("DB_REFERENCE_008", "참조 ERD 제약조건 일치 검증", not constraint_mismatches, failure_type="DB_CONSTRAINT_INVALID", message="DB 제약조건이 참조 ERD와 다릅니다.", target_agent=TARGET, target_scope=constraint_mismatches),
            make_check("DB_DDL_001", "DDL 생성 가능 구조 검증", not ddl_invalid, failure_type="DB_DDL_INVALID", message="DDL 식별자로 사용할 수 없는 컬럼명이 있습니다.", target_agent=TARGET, target_scope=ddl_invalid),
            _meeting_check(state),
        ]
    )
    return checks


def _reference_names(state: WorkflowState) -> tuple[set[str], set[tuple[str, str]]]:
    tables, columns = set(), set()
    for table in _reference_tables(state):
        if not isinstance(table, dict):
            continue
        table_name = str(table.get("physical_name") or table.get("table_name") or "")
        if table_name:
            tables.add(table_name)
        for column in table.get("columns", []):
            if isinstance(column, dict):
                columns.add((table_name, str(column.get("physical_name") or column.get("column_name") or "")))
    return tables, columns


def _reference_column_specs(state: WorkflowState) -> dict[tuple[str, str], dict[str, str]]:
    specs: dict[tuple[str, str], dict[str, str]] = {}
    for table in _reference_tables(state):
        if not isinstance(table, dict):
            continue
        table_name = str(table.get("physical_name") or table.get("table_name") or "")
        for column in table.get("columns", []):
            if not isinstance(column, dict):
                continue
            column_name = str(column.get("physical_name") or column.get("column_name") or "")
            if not table_name or not column_name:
                continue
            constraints = column.get("constraints") if isinstance(column.get("constraints"), list) else []
            is_pk = _contains_constraint(constraints, "PK") or _truthy(column.get("pk") or column.get("is_pk"))
            is_fk = _contains_constraint(constraints, "FK") or _truthy(column.get("fk") or column.get("is_fk"))
            is_idx = (
                _contains_constraint(constraints, "INDEX", "IDX")
                or _truthy(column.get("idx") or column.get("inx") or column.get("is_idx"))
                or is_pk
                or is_fk
            )
            specs[(table_name, column_name)] = {
                "column_logical_name": display_column_name(
                    column.get("logical_name") or column.get("column_logical_name"),
                    column_name,
                    table_name,
                    is_pk,
                ),
                "type_and_length": format_type_and_length(
                    column.get("type_and_length") or column.get("data_type"),
                    column.get("length"),
                ),
                "not_null": "Y" if not _nullable(column, default=True) else "",
                "pk": "Y" if is_pk else "",
                "fk": "Y" if is_fk else "",
                "idx": "Y" if is_idx else "",
                "default": _normalize_scalar(column.get("default")),
                "constraint": _constraint_text(column),
            }
    return specs


def _reference_tables(state: WorkflowState) -> list[dict[str, Any]]:
    references = state.get("agent_outputs", {}).get("document_merge_agent", {}).get("reference_erd_json_list") or []
    tables: list[dict[str, Any]] = []
    for item in references:
        if not isinstance(item, dict):
            continue
        nested = first_list(item, "tables", "entities", "erd_entity_json_list")
        if nested:
            tables.extend(table for table in nested if isinstance(table, dict))
        else:
            tables.append(item)
    return _normalize_reference_tables_without_generated_columns(tables)


def _normalize_reference_tables_without_generated_columns(
    tables: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized = normalize_erd_tables(tables)
    normalized_by_key = {
        str(table.get("physical_name") or table.get("table_name") or table.get("logical_name")): table
        for table in normalized
        if isinstance(table, dict)
    }
    result = []
    for original in tables:
        original_key = str(
            original.get("physical_name")
            or original.get("table_name")
            or original.get("logical_name")
            or ""
        )
        table = normalized_by_key.get(original_key)
        if table is None and original.get("physical_name"):
            table = normalized_by_key.get(str(original.get("physical_name")))
        if table is None:
            continue
        original_column_count = len(
            [
                column
                for column in original.get("columns", [])
                if isinstance(column, dict)
            ]
        )
        if original_column_count:
            table = {
                **table,
                "columns": [
                    column
                    for column in table.get("columns", [])[:original_column_count]
                    if isinstance(column, dict)
                ],
            }
        result.append(table)
    return result


def _design_column_specs(tables: list[Any]) -> dict[tuple[str, str], dict[str, str]]:
    specs: dict[tuple[str, str], dict[str, str]] = {}
    for table in tables:
        if not isinstance(table, dict):
            continue
        table_name = str(table.get("table_name") or table.get("physical_name") or "")
        for column in table.get("columns", []):
            if not isinstance(column, dict):
                continue
            column_name = str(column.get("column_name") or column.get("physical_name") or "")
            if not table_name or not column_name:
                continue
            is_pk = _truthy(column.get("pk") or column.get("is_pk")) or _contains_constraint(column.get("constraints"), "PK")
            is_fk = _truthy(column.get("fk") or column.get("is_fk")) or _contains_constraint(column.get("constraints"), "FK")
            is_idx = _truthy(column.get("idx") or column.get("inx") or column.get("is_idx")) or _contains_constraint(column.get("constraints"), "PK", "FK", "INDEX", "IDX")
            specs[(table_name, column_name)] = {
                "column_logical_name": display_column_name(
                    column.get("column_logical_name") or column.get("logical_name") or column.get("description"),
                    column_name,
                    table_name,
                    is_pk,
                ),
                "type_and_length": format_type_and_length(
                    column.get("type_and_length") or column.get("data_type"),
                    column.get("length"),
                ),
                "not_null": "Y" if not _nullable(column, default=True) else "",
                "pk": "Y" if is_pk else "",
                "fk": "Y" if is_fk else "",
                "idx": "Y" if is_idx else "",
                "default": _normalize_scalar(column.get("default")),
                "constraint": _constraint_text(column),
            }
    return specs


def _compare_column_spec(
    reference_specs: dict[tuple[str, str], dict[str, str]],
    design_specs: dict[tuple[str, str], dict[str, str]],
    field: str,
) -> list[str]:
    mismatches = []
    for key, reference in reference_specs.items():
        design = design_specs.get(key)
        if not design:
            continue
        if _normalize_scalar(reference.get(field)) != _normalize_scalar(design.get(field)):
            table, column = key
            mismatches.append(f"{table}.{column}")
    return sorted(mismatches)


def _constraint_text(column: dict[str, Any]) -> str:
    explicit = column.get("constraint")
    if explicit not in (None, "", []):
        return _normalize_scalar(explicit)
    constraints = column.get("constraints") if isinstance(column.get("constraints"), list) else []
    filtered = [
        _normalize_scalar(item)
        for item in constraints
        if str(item).upper() not in {"PK", "PRIMARY KEY", "FK", "FOREIGN KEY", "INDEX", "IDX", "NOT NULL"}
    ]
    return "; ".join(item for item in filtered if item)


def _nullable(column: dict[str, Any], *, default: bool) -> bool:
    if "nullable" in column:
        value = column.get("nullable")
        if isinstance(value, str):
            return value.strip().upper() not in {"N", "NO", "FALSE", "0", "NOT NULL"}
        return bool(value)
    if _truthy(column.get("not_null")):
        return False
    return default


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().upper() in {"Y", "YES", "TRUE", "1", "PK", "FK", "IDX", "INDEX"}
    return bool(value)


def _contains_constraint(value: Any, *needles: str) -> bool:
    if not isinstance(value, list):
        return any(needle.upper() in str(value).upper() for needle in needles) if value else False
    return any(
        any(needle.upper() in str(item).upper() for needle in needles)
        for item in value
    )


def _normalize_scalar(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _meeting_check(state: WorkflowState) -> dict[str, Any]:
    artifact = state.get("agent_outputs", {}).get("document_merge_agent", {}).get("integrated_artifact_json_list")
    return make_check("DB_MEETING_001", "수정 회의록 반영 검증", state.get("udt_yn") != "Y" or bool(artifact), failure_type="DB_MEETING_CHANGE_MISSING", message="회의록이 반영된 DB 통합 산출물을 확인할 수 없습니다.", target_agent="document_merge_agent")


def _invalid_column_refs(items: list[Any], column_names: set[str], key: str) -> bool:
    for item in items:
        if not isinstance(item, dict):
            return True
        refs = item.get(key) or []
        if not isinstance(refs, list):
            return True
        if any(str(ref) not in column_names for ref in refs):
            return True
    return False
