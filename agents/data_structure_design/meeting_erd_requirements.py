# ERD 수정 모드에서 회의록 변경 요구사항을 추출하고 ERD 반영 여부를 검증합니다.

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any


MEETING_ERD_REQUIREMENT_DEFINITIONS: list[dict[str, Any]] = [
    {
        "requirement_id": "MEETING_ERD_USER_ROLE_NM",
        "label": "사용자-권한 N:M 관계",
        "keywords": ["사용자-권한", "사용자 권한", "user role", "user_role", "N:M", "다대다"],
        "tables": ["tbl_user_role"],
        "relationships": [("tbl_user", "tbl_user_role"), ("tbl_role", "tbl_user_role")],
    },
    {
        "requirement_id": "MEETING_ERD_DOCUMENT_TAG_NM",
        "label": "문서-태그 N:M 관계",
        "keywords": ["문서-태그", "문서 태그", "document tag", "document_tag", "태그"],
        "tables": ["tbl_tag", "tbl_document_tag"],
        "relationships": [("tbl_document", "tbl_document_tag"), ("tbl_tag", "tbl_document_tag")],
    },
    {
        "requirement_id": "MEETING_ERD_AI_MODEL_EVAL",
        "label": "AI 모델 평가 결과",
        "keywords": ["AI 모델 평가", "모델 평가", "model eval", "model_eval", "평가 결과"],
        "tables": ["tbl_ai_model_eval"],
        "alternative_tables": ["tbl_model_eval_result"],
    },
    {
        "requirement_id": "MEETING_ERD_RAG_VERSION",
        "label": "RAG 버전 관리",
        "keywords": ["RAG 버전", "rag version", "rag_version", "버전 관리"],
        "tables": ["tbl_rag_version"],
    },
    {
        "requirement_id": "MEETING_ERD_JOB_LOG",
        "label": "작업 실행 로그",
        "keywords": ["작업 실행 로그", "job log", "job_log", "실행 로그"],
        "tables": ["tbl_job_log"],
    },
    {
        "requirement_id": "MEETING_ERD_NOTIFICATION",
        "label": "사용자 알림",
        "keywords": ["사용자 알림", "알림", "notification"],
        "tables": ["tbl_notification"],
    },
    {
        "requirement_id": "MEETING_ERD_USER_ORG",
        "label": "조직-사용자 관계",
        "keywords": [
            "조직-사용자",
            "조직 사용자",
            "사용자 조직",
            "조직별 사용자",
            "조직별 관리자",
            "하나의 조직",
            "조직에 소속",
            "조직은 여러 명의 사용자",
            "org_sn",
            "user org",
            "user_org",
        ],
        "tables": [],
        "alternative_tables": ["tbl_user_org"],
        "columns": [{"table": "tbl_user", "column": "org_sn"}],
        "relationships": [("tbl_org", "tbl_user"), ("tbl_org", "tbl_user_org"), ("tbl_user", "tbl_user_org")],
    },
]


def extract_meeting_erd_requirements(changes: list[Any]) -> list[dict[str, Any]]:
    text = _meeting_text(changes)
    if not text:
        return []
    extracted = []
    for definition in MEETING_ERD_REQUIREMENT_DEFINITIONS:
        if any(str(keyword).lower() in text for keyword in definition["keywords"]):
            extracted.append(_requirement_from_definition(definition, changes))
    return extracted


def apply_meeting_erd_requirements(
    tables: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    requirements: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    updated_tables = [deepcopy(table) for table in tables if isinstance(table, dict)]
    updated_relationships = [deepcopy(relation) for relation in relationships if isinstance(relation, dict)]
    report = {
        "meeting_change_requirements": requirements,
        "added_tables": [],
        "added_columns": [],
        "added_relationships": [],
    }

    for requirement in requirements:
        for table_name in requirement.get("required_tables", []):
            if not _has_table(updated_tables, table_name):
                updated_tables.append(_template_table(table_name, requirement["label"]))
                report["added_tables"].append(table_name)
        for column_requirement in requirement.get("required_columns", []):
            table_name = column_requirement.get("table")
            column_name = column_requirement.get("column")
            if table_name and column_name:
                table = _find_table(updated_tables, table_name)
                if table is None:
                    table = _template_table(table_name, table_name)
                    updated_tables.append(table)
                    report["added_tables"].append(table_name)
                if not _has_column(table, column_name):
                    table.setdefault("columns", []).append(_template_column(column_name, "조직 번호", constraints=["FK"]))
                    report["added_columns"].append(f"{table_name}.{column_name}")
        for parent, child in requirement.get("required_relationships", []):
            if not _has_table(updated_tables, parent):
                updated_tables.append(_template_table(parent, parent))
                report["added_tables"].append(parent)
            if not _has_table(updated_tables, child):
                updated_tables.append(_template_table(child, child))
                report["added_tables"].append(child)
            if _has_table(updated_tables, parent) and _has_table(updated_tables, child):
                relation_key = f"{parent}->{child}"
                if not _has_relationship(updated_relationships, parent, child):
                    updated_relationships.append(_template_relationship(parent, child, len(updated_relationships) + 1))
                    report["added_relationships"].append(relation_key)

    return updated_tables, _dedupe_relationships(updated_relationships), report


def evaluate_meeting_erd_requirements(
    tables: list[Any],
    relationships: list[Any],
    requirements: list[dict[str, Any]],
) -> dict[str, Any]:
    table_names = {
        str(table.get("physical_name") or table.get("table_name") or "")
        for table in tables
        if isinstance(table, dict)
    }
    table_map = {
        str(table.get("physical_name") or table.get("table_name") or ""): table
        for table in tables
        if isinstance(table, dict)
    }
    relation_pairs = {
        (
            str(relation.get("parent_table") or relation.get("source") or relation.get("from") or ""),
            str(relation.get("child_table") or relation.get("target") or relation.get("to") or ""),
        )
        for relation in relationships
        if isinstance(relation, dict)
    }

    requirement_results = []
    missing_items: list[str] = []
    reflected_tables: list[str] = []
    reflected_columns: list[str] = []
    reflected_relationships: list[str] = []

    for requirement in requirements:
        missing_for_requirement = []
        reflected_for_requirement = {"tables": [], "columns": [], "relationships": []}

        table_satisfied = True
        for table_name in requirement.get("required_tables", []):
            alternatives = set(requirement.get("alternative_tables", []))
            if table_name in table_names:
                reflected_tables.append(table_name)
                reflected_for_requirement["tables"].append(table_name)
            elif alternatives & table_names:
                reflected = sorted(alternatives & table_names)[0]
                reflected_tables.append(reflected)
                reflected_for_requirement["tables"].append(reflected)
            else:
                table_satisfied = False
                missing_for_requirement.append(table_name)

        for column_requirement in requirement.get("required_columns", []):
            table_name = str(column_requirement.get("table") or "")
            column_name = str(column_requirement.get("column") or "")
            table = table_map.get(table_name)
            alternative_tables = set(requirement.get("alternative_tables", []))
            alternative_reflected = bool(alternative_tables & table_names)
            if table and _has_column(table, column_name):
                item = f"{table_name}.{column_name}"
                reflected_columns.append(item)
                reflected_for_requirement["columns"].append(item)
            elif alternative_reflected:
                reflected = sorted(alternative_tables & table_names)[0]
                reflected_tables.append(reflected)
                reflected_for_requirement["tables"].append(reflected)
            else:
                table_satisfied = False
                missing_for_requirement.append(f"{table_name}.{column_name}")

        required_relationships = requirement.get("required_relationships", [])
        for parent, child in required_relationships:
            if (parent, child) in relation_pairs:
                item = f"{parent}->{child}"
                reflected_relationships.append(item)
                reflected_for_requirement["relationships"].append(item)
            else:
                table_satisfied = False
                missing_for_requirement.append(f"{parent}->{child}")

        if missing_for_requirement:
            missing_items.extend(missing_for_requirement)
        requirement_results.append(
            {
                "requirement_id": requirement["requirement_id"],
                "label": requirement["label"],
                "status": "PASS" if table_satisfied else "FAIL",
                "missing_items": missing_for_requirement,
                "reflected": reflected_for_requirement,
            }
        )

    return {
        "meeting_change_requirements": requirements,
        "requirement_results": requirement_results,
        "missing_items": list(dict.fromkeys(missing_items)),
        "reflected_tables": list(dict.fromkeys(reflected_tables)),
        "reflected_columns": list(dict.fromkeys(reflected_columns)),
        "reflected_relationships": list(dict.fromkeys(reflected_relationships)),
    }


def _requirement_from_definition(definition: dict[str, Any], changes: list[Any]) -> dict[str, Any]:
    return {
        "requirement_id": definition["requirement_id"],
        "label": definition["label"],
        "required_tables": list(definition.get("tables", [])),
        "alternative_tables": list(definition.get("alternative_tables", [])),
        "required_columns": list(definition.get("columns", [])),
        "required_relationships": list(definition.get("relationships", [])),
        "source_change_ids": _source_change_ids(changes),
    }


def _meeting_text(changes: list[Any]) -> str:
    return json.dumps(changes, ensure_ascii=False).lower()


def _source_change_ids(changes: list[Any]) -> list[str]:
    ids = []
    for index, change in enumerate(changes, start=1):
        if isinstance(change, dict):
            value = change.get("change_id") or change.get("id") or change.get("meeting_id")
            ids.append(str(value or f"CHANGE-{index:03d}"))
        else:
            ids.append(f"CHANGE-{index:03d}")
    return ids


def _has_table(tables: list[dict[str, Any]], table_name: str) -> bool:
    return _find_table(tables, table_name) is not None


def _find_table(tables: list[dict[str, Any]], table_name: str) -> dict[str, Any] | None:
    for table in tables:
        if str(table.get("physical_name") or table.get("table_name") or "") == table_name:
            return table
    return None


def _has_column(table: dict[str, Any], column_name: str) -> bool:
    return any(
        isinstance(column, dict)
        and str(column.get("physical_name") or column.get("column_name") or "") == column_name
        for column in table.get("columns", [])
    )


def _has_relationship(relationships: list[dict[str, Any]], parent: str, child: str) -> bool:
    return any(
        str(relation.get("parent_table") or relation.get("source") or relation.get("from") or "") == parent
        and str(relation.get("child_table") or relation.get("target") or relation.get("to") or "") == child
        for relation in relationships
    )


def _template_table(table_name: str, label: str) -> dict[str, Any]:
    logical_name = _logical_table_name(table_name, label)
    base = table_name.removeprefix("tbl_")
    return {
        "logical_name": logical_name,
        "physical_name": table_name,
        "description": f"{logical_name} 정보를 관리하는 테이블입니다.",
        "source_requirement_ids": [],
        "meeting_reflected": True,
        "columns": [
            _template_column(f"{base}_sn", f"{logical_name} 번호", constraints=["PK"], nullable=False),
            _template_column(f"{base}_nm", f"{logical_name}명", data_type="VARCHAR", length="200"),
            _template_column(f"{base}_cn", f"{logical_name} 내용", data_type="TEXT"),
            _template_column("use_yn", "사용 여부", data_type="CHAR", length="1", default="Y"),
            _template_column("reg_dt", "등록 일시", data_type="TIMESTAMP", nullable=False),
            _template_column("mdfcn_dt", "수정 일시", data_type="TIMESTAMP"),
        ],
    }


def _template_column(
    physical_name: str,
    logical_name: str,
    *,
    data_type: str = "BIGINT",
    length: str = "",
    constraints: list[str] | None = None,
    nullable: bool = True,
    default: str | None = None,
) -> dict[str, Any]:
    return {
        "logical_name": logical_name,
        "physical_name": physical_name,
        "data_type": data_type,
        "length": length,
        "nullable": nullable,
        "constraints": constraints or [],
        "default": default,
        "description": logical_name,
    }


def _template_relationship(parent: str, child: str, index: int) -> dict[str, Any]:
    return {
        "relationship_id": f"REL-MEETING-{index:03d}",
        "parent_table": parent,
        "child_table": child,
        "relationship_type": "1:N",
        "label": "references",
        "meeting_reflected": True,
    }


def _logical_table_name(table_name: str, label: str) -> str:
    mapping = {
        "tbl_user_role": "사용자 권한",
        "tbl_tag": "태그",
        "tbl_document_tag": "문서 태그",
        "tbl_ai_model_eval": "AI 모델 평가 결과",
        "tbl_model_eval_result": "모델 평가 결과",
        "tbl_rag_version": "RAG 버전",
        "tbl_job_log": "작업 실행 로그",
        "tbl_notification": "사용자 알림",
        "tbl_user_org": "사용자 조직",
        "tbl_role": "권한",
        "tbl_org": "조직",
    }
    return mapping.get(table_name, label)


def _dedupe_relationships(relationships: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped = []
    seen = set()
    for relationship in relationships:
        key = (
            str(relationship.get("parent_table") or ""),
            str(relationship.get("child_table") or ""),
            str(relationship.get("relationship_type") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(relationship)
    return deduped
