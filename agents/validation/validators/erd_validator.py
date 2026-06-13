# ERD 설계서의 구조와 관계를 검증합니다.

import re
from typing import Any

from agents.validation.schemas import duplicate_values, first_list, is_empty, make_check, missing_fields, missing_keys
from workflow.state import WorkflowState


TARGET = "data_structure_design_agent"


def validate(state: WorkflowState) -> list[dict[str, Any]]:
    outputs = state.get("agent_outputs", {})
    data_output = outputs.get(TARGET, {})
    entity_doc = data_output.get("erd_entity_json")
    mermaid_doc = data_output.get("erd_mermaid_json")
    tables = first_list(entity_doc, "tables", "entities", "erd_entity_json_list")
    checks = [
        make_check("ERD_OUTPUT_001", "ERD 출력 존재 검증", not is_empty(entity_doc) and not is_empty(mermaid_doc), failure_type="ERD_OUTPUT_MISSING", message="erd_entity_json 또는 erd_mermaid_json이 누락되었습니다.", target_agent=TARGET)
    ]
    if not tables:
        checks.append(make_check("ERD_SCHEMA_001", "ERD 테이블 Schema 검증", False, failure_type="ERD_SCHEMA_ERROR", message="ERD 테이블 목록이 없거나 구조가 올바르지 않습니다.", target_agent=TARGET))
        return checks + _mermaid_checks(outputs)

    table_missing, column_missing, column_duplicates, pk_missing, naming_errors = [], [], [], [], []
    for index, table in enumerate(tables):
        scope = str(table.get("table_id") or table.get("physical_name") or index) if isinstance(table, dict) else str(index)
        if not isinstance(table, dict) or missing_fields(table, ["table_id", "logical_name", "physical_name", "columns"]):
            table_missing.append(scope)
            continue
        columns = table["columns"] if isinstance(table["columns"], list) else []
        if any(not isinstance(column, dict) or missing_fields(column, ["column_id", "logical_name", "physical_name", "data_type"]) or missing_keys(column, ["nullable", "constraints"]) for column in columns):
            column_missing.append(scope)
        if duplicate_values(columns, "column_id", "physical_name"):
            column_duplicates.append(scope)
        if not any(_is_pk(column) for column in columns if isinstance(column, dict)):
            pk_missing.append(scope)
        if not re.fullmatch(r"[a-z][a-z0-9_]*", str(table.get("physical_name") or "")):
            naming_errors.append(scope)
        if any(not re.fullmatch(r"[a-z][a-z0-9_]*", str(column.get("physical_name") or "")) for column in columns if isinstance(column, dict)):
            naming_errors.append(scope)
    fk_invalid = _invalid_relationships(entity_doc, tables)
    coverage_missing = [
        str(table.get("table_id") or table.get("physical_name"))
        for table in tables if isinstance(table, dict) and is_empty(table.get("source_requirement_ids"))
    ]
    checks.extend(
        [
            make_check("ERD_SCHEMA_001", "ERD 필수 필드 검증", not table_missing and not column_missing, failure_type="ERD_SCHEMA_ERROR", message="테이블 또는 컬럼 필수 필드가 누락되었습니다.", target_agent=TARGET, target_scope=table_missing + column_missing),
            make_check("ERD_TABLE_001", "테이블명 중복 검증", not (duplicates := duplicate_values(tables, "table_id", "physical_name")), failure_type="ERD_TABLE_DUPLICATED", message="중복된 테이블명이 있습니다.", target_agent=TARGET, target_scope=duplicates),
            make_check("ERD_COLUMN_001", "컬럼명 중복 검증", not column_duplicates, failure_type="ERD_COLUMN_DUPLICATED", message="테이블 내부에 중복된 컬럼명이 있습니다.", target_agent=TARGET, target_scope=column_duplicates),
            make_check("ERD_PK_001", "PK 존재 검증", not pk_missing, failure_type="ERD_PK_MISSING", message="PK가 없는 테이블이 있습니다.", target_agent=TARGET, target_scope=pk_missing),
            make_check("ERD_FK_001", "FK 관계 정합성 검증", not fk_invalid, failure_type="ERD_FK_INVALID", message="존재하지 않는 테이블을 참조하는 관계가 있습니다.", target_agent=TARGET, target_scope=fk_invalid),
            make_check("ERD_COVERAGE_001", "요구사항 반영 추적성 검증", not coverage_missing, failure_type="ERD_REQUIREMENT_COVERAGE_MISSING", message="요구사항 출처가 없는 테이블이 있습니다.", target_agent=TARGET, target_scope=coverage_missing, severity="MEDIUM", warning=True),
            make_check("ERD_NAMING_001", "테이블/컬럼 표준명 검증", not naming_errors, failure_type="ERD_STANDARD_NAMING_ERROR", message="물리명이 snake_case 표준을 따르지 않습니다.", target_agent=TARGET, target_scope=sorted(set(naming_errors))),
        ]
    )
    return checks + _mermaid_checks(outputs)


def _is_pk(column: dict[str, Any]) -> bool:
    constraints = column.get("constraints")
    return bool(column.get("is_pk") or column.get("primary_key") or "PK" in str(constraints).upper())


def _invalid_relationships(document: Any, tables: list[Any]) -> list[str]:
    relationships = first_list(document, "relationships", "relations")
    names = {str(table.get("physical_name")) for table in tables if isinstance(table, dict)}
    invalid = []
    for index, relation in enumerate(relationships):
        if not isinstance(relation, dict):
            invalid.append(str(index))
            continue
        parent = str(relation.get("parent_table") or relation.get("source") or relation.get("from") or "")
        child = str(relation.get("child_table") or relation.get("target") or relation.get("to") or "")
        if parent not in names or child not in names:
            invalid.append(str(relation.get("relationship_id") or index))
    return invalid


def _mermaid_checks(outputs: dict[str, Any]) -> list[dict[str, Any]]:
    output = outputs.get("mermaid_generation_agent", {})
    return [
        make_check("ERD_MERMAID_001", "Mermaid 코드 존재 검증", not is_empty(output.get("mermaid_code")), failure_type="ERD_MERMAID_CODE_MISSING", message="ERD Mermaid 코드가 없습니다.", target_agent="mermaid_generation_agent"),
        make_check("ERD_MERMAID_002", "Mermaid 이미지 렌더링 검증", not is_empty(output.get("mermaid_image_path")), failure_type="ERD_MERMAID_RENDER_FAILED", message="ERD Mermaid 이미지 렌더링 결과가 없습니다.", target_agent="mermaid_generation_agent"),
    ]
