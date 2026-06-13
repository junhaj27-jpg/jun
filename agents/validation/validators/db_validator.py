# DB 설계서의 테이블과 컬럼 구조를 검증합니다.

from typing import Any

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
        if not isinstance(table.get("constraints"), list):
            constraint_invalid.append(scope)
        if not isinstance(table.get("indexes"), list):
            index_invalid.append(scope)
        if any(" " in str(column.get("column_name") or "") for column in columns if isinstance(column, dict)):
            ddl_invalid.append(scope)
    reference_tables, reference_columns = _reference_names(state)
    design_tables = {str(table.get("table_name")) for table in tables if isinstance(table, dict)}
    design_columns = {
        (str(table.get("table_name")), str(column.get("column_name")))
        for table in tables if isinstance(table, dict)
        for column in table.get("columns", []) if isinstance(column, dict)
    }
    missing_tables = sorted(reference_tables - design_tables)
    missing_reference_columns = sorted(f"{table}.{column}" for table, column in reference_columns - design_columns)
    checks.extend(
        [
            make_check("DB_SCHEMA_001", "DB 테이블 필수 필드 검증", not table_missing, failure_type="DB_SCHEMA_ERROR", message="테이블 필수 필드가 누락되었습니다.", target_agent=TARGET, target_scope=table_missing),
            make_check("DB_COLUMN_001", "DB 컬럼 검증", not column_missing, failure_type="DB_COLUMN_MISSING", message="컬럼 또는 컬럼 필수 필드가 누락되었습니다.", target_agent=TARGET, target_scope=column_missing),
            make_check("DB_TYPE_001", "데이터 타입 검증", not type_missing, failure_type="DB_DATA_TYPE_MISSING", message="데이터 타입이 누락된 컬럼이 있습니다.", target_agent=TARGET, target_scope=type_missing),
            make_check("DB_CONSTRAINT_001", "제약조건 구조 검증", not constraint_invalid, failure_type="DB_CONSTRAINT_INVALID", message="제약조건 구조가 올바르지 않습니다.", target_agent=TARGET, target_scope=constraint_invalid),
            make_check("DB_INDEX_001", "인덱스 구조 검증", not index_invalid, failure_type="DB_INDEX_INVALID", message="인덱스 구조가 올바르지 않습니다.", target_agent=TARGET, target_scope=index_invalid, severity="MEDIUM"),
            make_check("DB_REFERENCE_001", "참조 ERD 테이블 반영 검증", not missing_tables, failure_type="DB_TABLE_MISSING", message="참조 ERD 테이블이 DB 설계에 누락되었습니다.", target_agent=TARGET, target_scope=missing_tables),
            make_check("DB_REFERENCE_002", "참조 ERD 컬럼 반영 검증", not missing_reference_columns, failure_type="DB_COLUMN_MISSING", message="참조 ERD 컬럼이 DB 설계에 누락되었습니다.", target_agent=TARGET, target_scope=missing_reference_columns),
            make_check("DB_DDL_001", "DDL 생성 가능 구조 검증", not ddl_invalid, failure_type="DB_DDL_INVALID", message="DDL 식별자로 사용할 수 없는 컬럼명이 있습니다.", target_agent=TARGET, target_scope=ddl_invalid),
            _meeting_check(state),
        ]
    )
    return checks


def _reference_names(state: WorkflowState) -> tuple[set[str], set[tuple[str, str]]]:
    references = state.get("agent_outputs", {}).get("document_merge_agent", {}).get("reference_erd_json_list") or []
    tables, columns = set(), set()
    for table in references:
        if not isinstance(table, dict):
            continue
        table_name = str(table.get("physical_name") or table.get("table_name") or "")
        if table_name:
            tables.add(table_name)
        for column in table.get("columns", []):
            if isinstance(column, dict):
                columns.add((table_name, str(column.get("physical_name") or column.get("column_name") or "")))
    return tables, columns


def _meeting_check(state: WorkflowState) -> dict[str, Any]:
    artifact = state.get("agent_outputs", {}).get("document_merge_agent", {}).get("integrated_artifact_json_list")
    return make_check("DB_MEETING_001", "수정 회의록 반영 검증", state.get("udt_yn") != "Y" or bool(artifact), failure_type="DB_MEETING_CHANGE_MISSING", message="회의록이 반영된 DB 통합 산출물을 확인할 수 없습니다.", target_agent="document_merge_agent")
