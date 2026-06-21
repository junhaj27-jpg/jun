# ERD 설계서의 구조와 관계를 검증합니다.

import re
from typing import Any

from agents.validation.schemas import duplicate_values, first_list, is_empty, make_check, missing_fields, missing_keys
from agents.data_structure_design.meeting_erd_requirements import (
    evaluate_meeting_erd_requirements,
    extract_meeting_erd_requirements,
)
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
    generic_names, name_mismatches, attribute_mismatches, description_mismatches = [], [], [], []
    for index, table in enumerate(tables):
        scope = str(table.get("table_id") or table.get("physical_name") or index) if isinstance(table, dict) else str(index)
        entity_scope = _entity_scope(table, scope) if isinstance(table, dict) else scope
        if not isinstance(table, dict) or _missing_table_contract(table):
            table_missing.append(scope)
            continue
        entity_name = _entity_name(table)
        if _is_generic_entity_name(entity_name):
            generic_names.append(entity_scope)
        columns = table["columns"] if isinstance(table["columns"], list) else []
        inferred = _infer_entity_name_from_table(table)
        if inferred and entity_name and not _same_concept(entity_name, inferred):
            name_mismatches.append(entity_scope)
        if _description_mismatch(entity_name, table):
            description_mismatches.append(entity_scope)
        mismatched_columns = [
            _column_scope(entity_scope, column)
            for column in columns
            if isinstance(column, dict) and _attribute_mismatch(entity_name, column)
        ]
        attribute_mismatches.extend(mismatched_columns)
        if any(
            not isinstance(column, dict)
            or _missing_column_contract(column)
            or missing_keys(column, ["nullable", "constraints"])
            for column in columns
        ):
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
    meeting_check = _meeting_change_reflection_check(state, data_output, entity_doc, tables)
    checks.extend(
        [
            make_check("ERD_SCHEMA_001", "ERD 필수 필드 검증", not table_missing and not column_missing, failure_type="ERD_SCHEMA_ERROR", message="테이블 또는 컬럼 필수 필드가 누락되었습니다.", target_agent=TARGET, target_scope=table_missing + column_missing),
            make_check("ERD_TABLE_001", "테이블명 중복 검증", not (duplicates := duplicate_values(tables, "physical_name")), failure_type="ERD_TABLE_DUPLICATED", message="중복된 테이블명이 있습니다.", target_agent=TARGET, target_scope=duplicates),
            make_check("ERD_COLUMN_001", "컬럼명 중복 검증", not column_duplicates, failure_type="ERD_COLUMN_DUPLICATED", message="테이블 내부에 중복된 컬럼명이 있습니다.", target_agent=TARGET, target_scope=column_duplicates),
            make_check("ERD_PK_001", "PK 존재 검증", not pk_missing, failure_type="ERD_PK_MISSING", message="PK가 없는 테이블이 있습니다.", target_agent=TARGET, target_scope=pk_missing),
            make_check("ERD_FK_001", "FK 관계 정합성 검증", not fk_invalid, failure_type="ERD_FK_INVALID", message="존재하지 않는 테이블을 참조하는 관계가 있습니다.", target_agent=TARGET, target_scope=fk_invalid),
            make_check("ERD_COVERAGE_001", "요구사항 반영 추적성 검증", not coverage_missing, failure_type="ERD_REQUIREMENT_COVERAGE_MISSING", message="요구사항 출처가 없는 테이블이 있습니다.", target_agent=TARGET, target_scope=coverage_missing, severity="MEDIUM", warning=True),
            make_check("ERD_NAMING_001", "테이블/컬럼 표준명 검증", not naming_errors, failure_type="ERD_STANDARD_NAMING_ERROR", message="물리명이 snake_case 표준을 따르지 않습니다.", target_agent=TARGET, target_scope=sorted(set(naming_errors))),
            make_check("ERD_ENTITY_001", "Generic 엔티티명 검증", not generic_names, failure_type="ENTITY_GENERIC_NAME", message="generic entity_name은 사용할 수 없습니다.", target_agent=TARGET, target_scope=generic_names),
            make_check("ERD_ENTITY_002", "엔티티명-구조 정합성 검증", not name_mismatches, failure_type="ENTITY_NAME_MISMATCH", message="엔티티명과 설명/대표 속성의 핵심 개념이 다릅니다.", target_agent=TARGET, target_scope=name_mismatches),
            make_check("ERD_ENTITY_003", "엔티티-속성 정합성 검증", not attribute_mismatches, failure_type="ENTITY_ATTRIBUTE_MISMATCH", message="엔티티명과 맞지 않는 대표 속성이 있습니다.", target_agent=TARGET, target_scope=attribute_mismatches),
            make_check("ERD_ENTITY_004", "엔티티-설명 정합성 검증", not description_mismatches, failure_type="ENTITY_DESCRIPTION_MISMATCH", message="엔티티명과 설명의 핵심 개념이 다릅니다.", target_agent=TARGET, target_scope=description_mismatches),
        ]
    )
    if meeting_check is not None:
        checks.append(meeting_check)
    return checks + _mermaid_checks(outputs)


def _is_pk(column: dict[str, Any]) -> bool:
    constraints = column.get("constraints")
    return bool(column.get("is_pk") or column.get("primary_key") or "PK" in str(constraints).upper())


def _missing_table_contract(table: dict[str, Any]) -> bool:
    return bool(
        missing_fields(table, ["table_id", "columns"])
        or is_empty(table.get("entity_name") or table.get("logical_name"))
        or is_empty(table.get("table_name") or table.get("physical_name"))
    )


def _missing_column_contract(column: dict[str, Any]) -> bool:
    return bool(
        missing_fields(column, ["column_id", "data_type"])
        or is_empty(column.get("attribute_name") or column.get("logical_name") or column.get("column_logical_name"))
        or is_empty(column.get("column_name") or column.get("physical_name"))
    )


def _entity_name(table: dict[str, Any]) -> str:
    return str(table.get("entity_name") or table.get("logical_name") or "").strip()


def _entity_scope(table: dict[str, Any], fallback: str) -> str:
    return str(table.get("entity_id") or fallback)


def _is_generic_entity_name(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return True
    return bool(
        re.fullmatch(
            r"(?:엔티티|entity|table|테이블|데이터|정보|객체|항목|관리|업무)(?:\s*\d+)?",
            text,
        )
    )


def _infer_entity_name_from_table(table: dict[str, Any]) -> str:
    table_name = _entity_from_table_name(table.get("physical_name") or table.get("table_name"))
    if table_name:
        return table_name
    description_concepts = _concepts_from_text(
        table.get("entity_description") or table.get("description") or table.get("table_description")
    )
    if len(description_concepts) == 1:
        return next(iter(description_concepts))
    for column in table.get("columns", []):
        if not isinstance(column, dict):
            continue
        candidate = _known_entity_from_attribute_name(
            column.get("attribute_name")
            or column.get("logical_name")
            or column.get("column_logical_name")
        )
        if candidate:
            return candidate
    return ""


def _description_mismatch(entity_name: str, table: dict[str, Any]) -> bool:
    if not entity_name or _is_generic_entity_name(entity_name):
        return False
    entity_concepts = _concepts_from_text(entity_name)
    description_concepts = _concepts_from_text(
        table.get("entity_description") or table.get("description") or table.get("table_description")
    )
    if not entity_concepts or not description_concepts:
        return False
    return entity_concepts.isdisjoint(description_concepts)


def _attribute_mismatch(entity_name: str, column: dict[str, Any]) -> bool:
    if not entity_name or _is_generic_entity_name(entity_name):
        return False
    constraints = {str(value).upper() for value in column.get("constraints") or []}
    if column.get("fk") or column.get("is_fk") or "FK" in constraints:
        return False
    attr = str(column.get("attribute_name") or column.get("logical_name") or column.get("column_logical_name") or "").strip()
    if _is_common_attribute(attr):
        return False
    entity_concepts = _concepts_from_text(entity_name)
    attribute_concepts = _concepts_from_text(_entity_from_attribute_name(attr))
    if not entity_concepts or not attribute_concepts:
        return False
    return entity_concepts.isdisjoint(attribute_concepts)


def _entity_from_attribute_name(value: Any) -> str:
    text = str(value or "").strip()
    for suffix in ("일련번호", "번호", "ID", "아이디", "명", "이름", "내용", "상태코드", "상태 코드", "코드"):
        if text.endswith(suffix) and len(text) > len(suffix):
            return text[: -len(suffix)].strip()
    return ""


def _known_entity_from_attribute_name(value: Any) -> str:
    candidate = _entity_from_attribute_name(value)
    concepts = _concepts_from_text(candidate)
    if len(concepts) == 1:
        return next(iter(concepts))
    return ""


def _concepts_from_text(value: Any) -> set[str]:
    text = str(value or "").strip()
    lower = text.lower()
    concepts: set[str] = set()
    keyword_groups = {
        "agent": ("agent", "에이전트"),
        "rag": ("rag",),
        "aimodel": ("ai 모델", "ai모델", "llm 모델", "llm모델"),
        "user": ("사용자", "user"),
        "customer": ("고객", "customer"),
        "document": ("문서", "document", "docs"),
        "file": ("파일", "file"),
        "org": ("조직", "organization", "org"),
        "role": ("권한", "역할", "role"),
        "tag": ("태그", "tag"),
        "notification": ("알림", "notification"),
        "job": ("작업", "job"),
        "log": ("로그", "log"),
    }
    normalized = re.sub(r"[\s_-]+", "", lower)
    for concept, keywords in keyword_groups.items():
        if any(re.sub(r"[\s_-]+", "", keyword.lower()) in normalized for keyword in keywords):
            concepts.add(concept)
    return concepts


def _entity_from_table_name(value: Any) -> str:
    text = str(value or "").strip().lower().removeprefix("tbl_")
    if not text:
        return ""
    aliases = {
        "agent": "Agent",
        "user": "사용자",
        "customer": "고객",
        "document": "문서",
        "docs": "문서",
        "file": "파일",
        "role": "권한",
        "org": "조직",
        "organization": "조직",
        "tag": "태그",
        "notification": "알림",
        "job": "작업",
        "log": "로그",
    }
    for key, label in aliases.items():
        if text == key or text.startswith(f"{key}_") or text.endswith(f"_{key}"):
            return label
    return ""


def _same_concept(left: str, right: str) -> bool:
    left_concepts = _concepts_from_text(left)
    right_concepts = _concepts_from_text(right)
    if left_concepts and right_concepts:
        return not left_concepts.isdisjoint(right_concepts)
    left_key = _concept_key(left)
    right_key = _concept_key(right)
    return bool(left_key and right_key and (left_key == right_key or left_key in right_key or right_key in left_key))


def _concept_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[\s_-]+", "", text)
    aliases = {
        "에이전트": "agent",
        "agent": "agent",
        "사용자": "user",
        "고객": "customer",
        "문서": "document",
        "docs": "document",
        "document": "document",
        "파일": "file",
        "권한": "role",
        "역할": "role",
        "조직": "org",
        "태그": "tag",
        "알림": "notification",
        "작업": "job",
        "로그": "log",
        "rag": "rag",
        "ai모델": "aimodel",
        "model": "aimodel",
    }
    return aliases.get(text, text)


def _is_common_attribute(value: Any) -> bool:
    compact = re.sub(r"\s+", "", str(value or ""))
    if compact in {
        "ID",
        "일련번호",
        "번호",
        "사용여부",
        "등록일시",
        "수정일시",
        "생성일시",
        "상태코드",
        "상태",
        "코드",
        "내용",
        "설명",
        "명",
    }:
        return True
    return bool(
        re.search(
            r"(?:등록|수정|생성|삭제|처리|승인|요청|응답|최종|최초)"
            r"(?:자|자명|자ID|자아이디|일시|일자|일|시간|내용|결과|상태|여부|사유)$",
            compact,
            re.IGNORECASE,
        )
    )


def _column_scope(table_scope: str, column: dict[str, Any]) -> str:
    return f"{table_scope}.{column.get('column_id') or column.get('physical_name') or column.get('logical_name')}"


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


def _meeting_change_reflection_check(
    state: WorkflowState,
    data_output: dict[str, Any],
    entity_doc: Any,
    tables: list[Any],
) -> dict[str, Any] | None:
    if str(state.get("udt_yn", "")).upper() != "Y":
        return None
    requirements = data_output.get("meeting_change_requirements")
    if not isinstance(requirements, list):
        changes = state.get("agent_outputs", {}).get("document_merge_agent", {}).get("meeting_change_items")
        requirements = extract_meeting_erd_requirements(changes if isinstance(changes, list) else [])
    if not requirements:
        return None
    relationships = first_list(entity_doc, "relationships", "relations")
    reflection = evaluate_meeting_erd_requirements(tables, relationships, requirements)
    missing_items = reflection["missing_items"]
    check = make_check(
        "ERD_MEETING_001",
        "회의록 데이터 구조 변경 반영 검증",
        not missing_items,
        failure_type="ERD_MEETING_CHANGE_MISSING",
        message="회의록에서 요구한 신규/변경 데이터 구조가 ERD에 누락되었습니다.",
        target_agent=TARGET,
        target_scope=missing_items,
    )
    check["meeting_change_requirements"] = reflection["meeting_change_requirements"]
    check["requirement_results"] = reflection["requirement_results"]
    check["missing_items"] = missing_items
    check["reflected_tables"] = reflection["reflected_tables"]
    check["reflected_columns"] = reflection["reflected_columns"]
    check["reflected_relationships"] = reflection["reflected_relationships"]
    return check
