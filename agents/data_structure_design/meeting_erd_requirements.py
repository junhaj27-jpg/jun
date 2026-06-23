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
        "columns": [
            {"table": "tbl_user_role", "column": "grant_dt", "logical_name": "부여 일시", "data_type": "DATETIME", "nullable": False},
            {"table": "tbl_user_role", "column": "expire_dt", "logical_name": "만료 일시", "data_type": "DATETIME"},
            {"table": "tbl_user_role", "column": "use_yn", "logical_name": "사용 여부", "data_type": "CHAR", "length": "1", "nullable": False, "default": "Y"},
        ],
        "relationships": [("tbl_user", "tbl_user_role"), ("tbl_role", "tbl_user_role")],
        "relationship_details": [
            {
                "from": "tbl_user",
                "to": "tbl_role",
                "type": "N:M",
                "via": "tbl_user_role",
            }
        ],
    },
    {
        "requirement_id": "MEETING_ERD_DOCUMENT_TAG_NM",
        "label": "문서-태그 N:M 관계",
        "keywords": ["문서-태그", "문서 태그", "document tag", "document_tag", "태그"],
        "tables": ["tbl_tag", "tbl_document_tag"],
        "columns": [
            {"table": "tbl_tag", "column": "tag_nm", "logical_name": "태그명", "data_type": "VARCHAR", "length": "200", "nullable": False},
            {"table": "tbl_tag", "column": "color_cd", "logical_name": "색상 코드", "data_type": "VARCHAR", "length": "30"},
            {"table": "tbl_tag", "column": "tag_cn", "logical_name": "태그 설명", "data_type": "TEXT"},
        ],
        "relationships": [("tbl_document", "tbl_document_tag"), ("tbl_tag", "tbl_document_tag")],
        "relationship_details": [
            {
                "from": "tbl_document",
                "to": "tbl_tag",
                "type": "N:M",
                "via": "tbl_document_tag",
            }
        ],
    },
    {
        "requirement_id": "MEETING_ERD_AI_MODEL_EVAL",
        "label": "AI 모델 평가 결과",
        "keywords": ["AI 모델 평가", "모델 평가", "model eval", "model_eval", "평가 결과"],
        "tables": ["tbl_ai_model_eval"],
        "alternative_tables": ["tbl_model_eval_result"],
        "columns": [
            {"table": "tbl_ai_model_eval", "column": "eval_nm", "logical_name": "평가명", "data_type": "VARCHAR", "length": "200", "nullable": False},
            {"table": "tbl_ai_model_eval", "column": "accuracy_rt", "logical_name": "정확도", "data_type": "DECIMAL", "length": "7,4"},
            {"table": "tbl_ai_model_eval", "column": "response_ms", "logical_name": "응답 속도", "data_type": "BIGINT"},
            {"table": "tbl_ai_model_eval", "column": "eval_score", "logical_name": "평가 점수", "data_type": "DECIMAL", "length": "7,2"},
            {"table": "tbl_ai_model_eval", "column": "eval_dt", "logical_name": "평가 일시", "data_type": "DATETIME", "nullable": False},
        ],
        "relationships": [("tbl_model_ai", "tbl_ai_model_eval")],
        "relationship_details": [
            {"from": "tbl_model_ai", "to": "tbl_ai_model_eval", "type": "1:N", "via": None}
        ],
    },
    {
        "requirement_id": "MEETING_ERD_RAG_VERSION",
        "label": "RAG 버전 관리",
        "keywords": ["RAG 버전", "rag version", "rag_version", "버전 관리"],
        "tables": ["tbl_rag_version"],
        "columns": [
            {"table": "tbl_rag_version", "column": "version_no", "logical_name": "버전 번호", "data_type": "VARCHAR", "length": "50", "nullable": False},
            {"table": "tbl_rag_version", "column": "change_rsn", "logical_name": "변경 사유", "data_type": "TEXT"},
            {"table": "tbl_rag_version", "column": "use_yn", "logical_name": "활성 여부", "data_type": "CHAR", "length": "1", "nullable": False, "default": "Y"},
            {"table": "tbl_rag_version", "column": "deploy_dt", "logical_name": "배포 일시", "data_type": "DATETIME"},
        ],
        "relationships": [("tbl_rag", "tbl_rag_version")],
        "relationship_details": [
            {"from": "tbl_rag", "to": "tbl_rag_version", "type": "1:N", "via": None}
        ],
    },
    {
        "requirement_id": "MEETING_ERD_JOB_LOG",
        "label": "작업 실행 로그",
        "keywords": ["작업 실행 로그", "job log", "job_log", "실행 로그"],
        "tables": ["tbl_job_log"],
        "columns": [
            {"table": "tbl_job_log", "column": "log_level_cd", "logical_name": "로그 레벨", "data_type": "VARCHAR", "length": "20", "nullable": False},
            {"table": "tbl_job_log", "column": "message_cn", "logical_name": "메시지", "data_type": "TEXT"},
            {"table": "tbl_job_log", "column": "exec_dt", "logical_name": "실행 일시", "data_type": "DATETIME", "nullable": False},
            {"table": "tbl_job_log", "column": "elapsed_ms", "logical_name": "소요 시간", "data_type": "BIGINT"},
        ],
        "relationships": [("tbl_job", "tbl_job_log")],
        "relationship_details": [
            {"from": "tbl_job", "to": "tbl_job_log", "type": "1:N", "via": None}
        ],
    },
    {
        "requirement_id": "MEETING_ERD_NOTIFICATION",
        "label": "사용자 알림",
        "keywords": ["사용자 알림", "알림", "notification"],
        "tables": ["tbl_notification"],
        "columns": [
            {"table": "tbl_notification", "column": "notification_type_cd", "logical_name": "알림 유형", "data_type": "VARCHAR", "length": "30", "nullable": False},
            {"table": "tbl_notification", "column": "title_nm", "logical_name": "제목", "data_type": "VARCHAR", "length": "300", "nullable": False},
            {"table": "tbl_notification", "column": "notification_cn", "logical_name": "내용", "data_type": "TEXT", "nullable": False},
            {"table": "tbl_notification", "column": "read_yn", "logical_name": "읽음 여부", "data_type": "CHAR", "length": "1", "nullable": False, "default": "N"},
            {"table": "tbl_notification", "column": "sent_dt", "logical_name": "발송 일시", "data_type": "DATETIME"},
        ],
        "relationships": [("tbl_user", "tbl_notification")],
        "relationship_details": [
            {"from": "tbl_user", "to": "tbl_notification", "type": "1:N", "via": None}
        ],
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
        "columns": [
            {"table": "tbl_user", "column": "org_sn", "logical_name": "조직 일련번호", "data_type": "BIGINT", "nullable": False, "constraints": ["FK"]},
            {"table": "tbl_user", "column": "org_admin_yn", "logical_name": "조직 관리자 여부", "data_type": "CHAR", "length": "1", "nullable": False, "default": "N"},
        ],
        "relationships": [("tbl_org", "tbl_user"), ("tbl_org", "tbl_user_org"), ("tbl_user", "tbl_user_org")],
        "relationship_details": [
            {"from": "tbl_org", "to": "tbl_user", "type": "1:N", "via": None}
        ],
    },
]


def extract_meeting_erd_requirements(changes: list[Any]) -> list[dict[str, Any]]:
    text = _meeting_text(changes)
    if not text:
        return []
    extracted = _extract_structured_requirements(changes)
    extracted_ids = {
        str(item.get("requirement_id") or "")
        for item in extracted
        if isinstance(item, dict)
    }
    for definition in MEETING_ERD_REQUIREMENT_DEFINITIONS:
        if (
            definition["requirement_id"] not in extracted_ids
            and any(str(keyword).lower() in text for keyword in definition["keywords"])
        ):
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
                    table.setdefault("columns", []).append(
                        _template_column(
                            column_name,
                            str(column_requirement.get("logical_name") or column_name),
                            data_type=str(column_requirement.get("data_type") or "BIGINT"),
                            length=str(column_requirement.get("length") or ""),
                            constraints=list(column_requirement.get("constraints") or []),
                            nullable=bool(column_requirement.get("nullable", True)),
                            default=column_requirement.get("default"),
                        )
                    )
                    report["added_columns"].append(f"{table_name}.{column_name}")
        for parent, child in requirement.get("required_relationships", []):
            parent_table = _find_table(updated_tables, parent)
            if parent_table is None:
                parent_table = _template_table(parent, parent)
                updated_tables.append(parent_table)
                report["added_tables"].append(parent)
            child_table = _find_table(updated_tables, child)
            if child_table is None:
                child_table = _template_table(child, child)
                updated_tables.append(child_table)
                report["added_tables"].append(child)
            if parent_table is not None and child_table is not None:
                actual_parent = _table_name(parent_table)
                actual_child = _table_name(child_table)
                parent_column = _ensure_primary_key(parent_table)
                child_column = _ensure_foreign_key(child_table, parent_column, parent_table)
                relation_key = f"{actual_parent}->{actual_child}"
                if not _has_relationship(updated_relationships, actual_parent, actual_child):
                    updated_relationships.append(
                        _template_relationship(
                            actual_parent,
                            parent_column,
                            actual_child,
                            child_column,
                            len(updated_relationships) + 1,
                        )
                    )
                    report["added_relationships"].append(relation_key)

    return updated_tables, _dedupe_relationships(updated_relationships), report


def evaluate_meeting_erd_requirements(
    tables: list[Any],
    relationships: list[Any],
    requirements: list[dict[str, Any]],
) -> dict[str, Any]:
    table_names = {_table_name(table) for table in tables if isinstance(table, dict)}
    table_map = {_table_name(table): table for table in tables if isinstance(table, dict)}
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
            resolved = _resolve_existing_table_name(tables, table_name)
            if resolved:
                reflected_tables.append(resolved)
                reflected_for_requirement["tables"].append(resolved)
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
            resolved_table_name = _resolve_existing_table_name(tables, table_name)
            table = table_map.get(resolved_table_name)
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
            actual_parent = _resolve_existing_table_name(tables, parent) or parent
            actual_child = _resolve_existing_table_name(tables, child) or child
            if (actual_parent, actual_child) in relation_pairs:
                item = f"{actual_parent}->{actual_child}"
                reflected_relationships.append(item)
                reflected_for_requirement["relationships"].append(item)
            else:
                table_satisfied = False
                missing_for_requirement.append(f"{parent}->{child}")

        for relation_detail in requirement.get(
            "required_relationship_details",
            [],
        ):
            if not isinstance(relation_detail, dict):
                continue
            parent = str(relation_detail.get("from") or "")
            child = str(relation_detail.get("to") or "")
            via = str(relation_detail.get("via") or "")
            relation_type = str(
                relation_detail.get("type") or "1:N"
            ).upper()
            actual_parent = _resolve_existing_table_name(tables, parent) or parent
            actual_child = _resolve_existing_table_name(tables, child) or child
            actual_via = _resolve_existing_table_name(tables, via) if via else ""
            if relation_type in {"N:M", "M:N"}:
                nm_satisfied = bool(
                    actual_via
                    and (actual_parent, actual_via) in relation_pairs
                    and (actual_child, actual_via) in relation_pairs
                )
                item = f"{actual_parent}<->{actual_child} via {actual_via or via}"
            else:
                nm_satisfied = (actual_parent, actual_child) in relation_pairs
                item = f"{actual_parent}->{actual_child} {relation_type}"
            if nm_satisfied:
                reflected_relationships.append(item)
                reflected_for_requirement["relationships"].append(item)
            else:
                table_satisfied = False
                missing_for_requirement.append(item)

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


def build_erd_diff(
    before_tables: list[Any],
    before_relationships: list[Any],
    after_tables: list[Any],
    after_relationships: list[Any],
) -> dict[str, Any]:
    before_map = {
        _table_name(table): table
        for table in before_tables
        if isinstance(table, dict) and _table_name(table)
    }
    after_map = {
        _table_name(table): table
        for table in after_tables
        if isinstance(table, dict) and _table_name(table)
    }
    added_names = sorted(set(after_map) - set(before_map))
    removed_names = sorted(set(before_map) - set(after_map))
    modified_entities = []
    added_columns = []
    removed_columns = []
    modified_columns = []
    for table_name in sorted(set(before_map) & set(after_map)):
        before_columns = _column_map(before_map[table_name])
        after_columns = _column_map(after_map[table_name])
        table_added = sorted(set(after_columns) - set(before_columns))
        table_removed = sorted(set(before_columns) - set(after_columns))
        table_modified = sorted(
            column_name
            for column_name in set(before_columns) & set(after_columns)
            if _column_signature(before_columns[column_name])
            != _column_signature(after_columns[column_name])
        )
        if table_added or table_removed or table_modified:
            modified_entities.append(
                {
                    "entity": _logical_table_name_from_table(after_map[table_name]),
                    "table_name": table_name,
                    "added_columns": table_added,
                    "removed_columns": table_removed,
                    "modified_columns": table_modified,
                }
            )
        added_columns.extend(f"{table_name}.{name}" for name in table_added)
        removed_columns.extend(f"{table_name}.{name}" for name in table_removed)
        modified_columns.extend(f"{table_name}.{name}" for name in table_modified)

    before_relations = {
        _relationship_identity(relation): _relationship_signature(relation)
        for relation in before_relationships
        if isinstance(relation, dict)
    }
    after_relations = {
        _relationship_identity(relation): _relationship_signature(relation)
        for relation in after_relationships
        if isinstance(relation, dict)
    }
    shared_relationships = set(before_relations) & set(after_relations)
    modified_relationships = sorted(
        identity
        for identity in shared_relationships
        if before_relations[identity] != after_relations[identity]
    )
    return {
        "added_entities": [
            {
                "table_name": name,
                "entity_name": _logical_table_name_from_table(after_map[name]),
            }
            for name in added_names
        ],
        "removed_entities": [
            {
                "table_name": name,
                "entity_name": _logical_table_name_from_table(before_map[name]),
            }
            for name in removed_names
        ],
        "modified_entities": modified_entities,
        "added_columns": added_columns,
        "removed_columns": removed_columns,
        "modified_columns": modified_columns,
        "added_relationships": sorted(set(after_relations) - set(before_relations)),
        "removed_relationships": sorted(set(before_relations) - set(after_relations)),
        "modified_relationships": modified_relationships,
    }


def build_requirement_coverage(
    tables: list[Any],
    relationships: list[Any],
    requirements: list[dict[str, Any]],
) -> dict[str, Any]:
    evaluated = evaluate_meeting_erd_requirements(tables, relationships, requirements)
    results = []
    for item in evaluated["requirement_results"]:
        applied = [
            *[f"엔티티 반영: {value}" for value in item["reflected"]["tables"]],
            *[f"컬럼 반영: {value}" for value in item["reflected"]["columns"]],
            *[f"관계 반영: {value}" for value in item["reflected"]["relationships"]],
        ]
        missing = list(item["missing_items"])
        status = "APPLIED" if not missing else ("PARTIAL" if applied else "MISSING")
        requirement = next(
            (
                value
                for value in requirements
                if value.get("requirement_id") == item.get("requirement_id")
            ),
            {},
        )
        results.append(
            {
                "requirement_id": item["requirement_id"],
                "title": item["label"],
                "status": status,
                "applied": applied,
                "missing": missing,
                "impact_entities": list(
                    dict.fromkeys(
                        [
                            *requirement.get("required_tables", []),
                            *requirement.get("alternative_tables", []),
                        ]
                    )
                ),
            }
        )
    return {
        "total": len(results),
        "applied": sum(item["status"] == "APPLIED" for item in results),
        "partial": sum(item["status"] == "PARTIAL" for item in results),
        "missing": sum(item["status"] == "MISSING" for item in results),
        "requirement_validation_results": results,
    }


def build_change_requirements_json(
    requirements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    for index, requirement in enumerate(requirements, start=1):
        grouped_columns: dict[str, list[str]] = {}
        for column in requirement.get("required_columns", []):
            if not isinstance(column, dict):
                continue
            table_name = str(column.get("table") or "")
            logical_name = str(
                column.get("logical_name")
                or column.get("column")
                or ""
            )
            if table_name and logical_name:
                grouped_columns.setdefault(table_name, []).append(logical_name)
        relationships = []
        for relation in requirement.get("required_relationship_details", []):
            if isinstance(relation, dict):
                relationships.append(dict(relation))
        if not relationships:
            relationships = [
                {
                    "from": parent,
                    "to": child,
                    "type": "1:N",
                    "via": None,
                }
                for parent, child in requirement.get("required_relationships", [])
            ]
        result.append(
            {
                "id": str(
                    requirement.get("requirement_id")
                    or f"CR-{index:03d}"
                ),
                "title": str(
                    requirement.get("label")
                    or requirement.get("title")
                    or ""
                ),
                "required_entities": list(
                    dict.fromkeys(
                        [
                            *requirement.get("required_tables", []),
                            *requirement.get("alternative_tables", []),
                            *[
                                value
                                for relation in relationships
                                for value in (
                                    relation.get("from"),
                                    relation.get("to"),
                                    relation.get("via"),
                                )
                                if value
                            ],
                        ]
                    )
                ),
                "required_columns": [
                    {"entity": table_name, "columns": columns}
                    for table_name, columns in grouped_columns.items()
                ],
                "required_relationships": relationships,
                "source_change_ids": list(
                    requirement.get("source_change_ids", [])
                ),
            }
        )
    return result


def _extract_structured_requirements(
    changes: list[Any],
) -> list[dict[str, Any]]:
    extracted = []
    for index, change in enumerate(changes, start=1):
        if not isinstance(change, dict):
            continue
        source = (
            change.get("change_requirement")
            if isinstance(change.get("change_requirement"), dict)
            else change
        )
        required_entities = source.get("required_entities")
        required_columns = source.get("required_columns")
        required_relationships = source.get("required_relationships")
        if not any(
            isinstance(value, list) and value
            for value in (
                required_entities,
                required_columns,
                required_relationships,
            )
        ):
            continue

        columns = []
        for column_group in required_columns or []:
            if not isinstance(column_group, dict):
                continue
            table_name = str(
                column_group.get("entity")
                or column_group.get("table")
                or ""
            )
            for column in column_group.get("columns", []):
                if isinstance(column, dict):
                    columns.append(
                        {
                            **column,
                            "table": table_name,
                            "column": str(
                                column.get("column")
                                or column.get("physical_name")
                                or column.get("name")
                                or ""
                            ),
                            "logical_name": str(
                                column.get("logical_name")
                                or column.get("name")
                                or column.get("column")
                                or ""
                            ),
                        }
                    )
                else:
                    columns.append(
                        {
                            "table": table_name,
                            "column": str(column),
                            "logical_name": str(column),
                        }
                    )

        relation_pairs = []
        relation_details = []
        for relation in required_relationships or []:
            if not isinstance(relation, dict):
                continue
            parent = str(
                relation.get("from")
                or relation.get("parent")
                or relation.get("parent_table")
                or ""
            )
            child = str(
                relation.get("to")
                or relation.get("child")
                or relation.get("child_table")
                or ""
            )
            via = str(relation.get("via") or "")
            relation_type = str(
                relation.get("type")
                or relation.get("relationship_type")
                or "1:N"
            )
            if parent and child:
                if relation_type.upper() in {"N:M", "M:N"} and via:
                    relation_pairs.extend([(parent, via), (child, via)])
                else:
                    relation_pairs.append((parent, child))
                relation_details.append(
                    {
                        "from": parent,
                        "to": child,
                        "type": relation_type,
                        "via": via or None,
                    }
                )

        extracted.append(
            {
                "requirement_id": str(
                    source.get("id")
                    or source.get("requirement_id")
                    or f"CR-{index:03d}"
                ),
                "label": str(
                    source.get("title")
                    or source.get("label")
                    or f"회의록 변경사항 {index}"
                ),
                "required_tables": [
                    str(item) for item in required_entities or [] if item
                ],
                "alternative_tables": [],
                "required_columns": columns,
                "required_relationships": relation_pairs,
                "required_relationship_details": relation_details,
                "source_change_ids": [
                    str(
                        change.get("change_id")
                        or change.get("id")
                        or f"CHANGE-{index:03d}"
                    )
                ],
            }
        )
    return extracted


def _column_map(table: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(column.get("physical_name") or column.get("column_name") or ""): column
        for column in table.get("columns", [])
        if isinstance(column, dict)
        and str(column.get("physical_name") or column.get("column_name") or "")
    }


def _column_signature(column: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(column.get("data_type") or ""),
        str(column.get("length") or ""),
        bool(column.get("nullable", True)),
        tuple(sorted(str(item).upper() for item in column.get("constraints", []))),
        str(column.get("default") or ""),
    )


def _relationship_signature(relation: dict[str, Any]) -> str:
    return "|".join(
        [
            str(relation.get("parent_table") or relation.get("to_table") or ""),
            str(relation.get("parent_column") or relation.get("to_column") or ""),
            str(relation.get("child_table") or relation.get("from_table") or ""),
            str(relation.get("child_column") or relation.get("from_column") or ""),
            str(relation.get("relationship_type") or ""),
        ]
    )


def _relationship_identity(relation: dict[str, Any]) -> str:
    return "->".join(
        [
            str(relation.get("parent_table") or relation.get("to_table") or ""),
            str(relation.get("child_table") or relation.get("from_table") or ""),
        ]
    )


def _logical_table_name_from_table(table: dict[str, Any]) -> str:
    return str(
        table.get("entity_name")
        or table.get("logical_name")
        or table.get("table_logical_name")
        or _table_name(table)
    )


def _requirement_from_definition(definition: dict[str, Any], changes: list[Any]) -> dict[str, Any]:
    return {
        "requirement_id": definition["requirement_id"],
        "label": definition["label"],
        "required_tables": list(definition.get("tables", [])),
        "alternative_tables": list(definition.get("alternative_tables", [])),
        "required_columns": list(definition.get("columns", [])),
        "required_relationships": list(definition.get("relationships", [])),
        "required_relationship_details": list(
            definition.get("relationship_details", [])
        ),
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
    requested_aliases = _table_aliases(table_name)
    for table in tables:
        if _table_aliases(_table_name(table)) & requested_aliases:
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


def _template_relationship(
    parent: str,
    parent_column: str,
    child: str,
    child_column: str,
    index: int,
) -> dict[str, Any]:
    return {
        "relationship_id": f"REL-MEETING-{index:03d}",
        "parent_table": parent,
        "parent_column": parent_column,
        "child_table": child,
        "child_column": child_column,
        "to_table": parent,
        "to_column": parent_column,
        "from_table": child,
        "from_column": child_column,
        "relationship_type": "1:N",
        "label": "references",
        "meeting_reflected": True,
    }


def _table_name(table: dict[str, Any]) -> str:
    return str(table.get("physical_name") or table.get("table_name") or "")


def _table_aliases(table_name: str) -> set[str]:
    normalized = str(table_name or "").strip().lower()
    aliases = {normalized}
    alias_groups = (
        {"tbl_docs", "tbl_document"},
        {"tbl_role", "tbl_auth_role"},
        {"tbl_org", "tbl_organization"},
    )
    for group in alias_groups:
        if normalized in group:
            aliases.update(group)
    return aliases


def _resolve_existing_table_name(tables: list[Any], table_name: str) -> str:
    table = _find_table(
        [item for item in tables if isinstance(item, dict)],
        table_name,
    )
    return _table_name(table) if table is not None else ""


def _ensure_primary_key(table: dict[str, Any]) -> str:
    for column in table.get("columns", []):
        if not isinstance(column, dict):
            continue
        constraints = {str(item).upper() for item in column.get("constraints", [])}
        if column.get("pk") in {"Y", True} or "PK" in constraints:
            return str(column.get("physical_name") or column.get("column_name") or "")
    table_name = _table_name(table)
    base = table_name.removeprefix("tbl_") or "entity"
    column_name = f"{base}_sn"
    table.setdefault("columns", []).insert(
        0,
        _template_column(
            column_name,
            f"{table.get('logical_name') or table.get('entity_name') or base} 일련번호",
            constraints=["PK", "AUTO_INCREMENT"],
            nullable=False,
        ),
    )
    return column_name


def _ensure_foreign_key(
    child_table: dict[str, Any],
    parent_column: str,
    parent_table: dict[str, Any],
) -> str:
    parent_base = _table_name(parent_table).removeprefix("tbl_")
    child_column = parent_column or f"{parent_base}_sn"
    if not _has_column(child_table, child_column):
        logical_parent = str(
            parent_table.get("logical_name")
            or parent_table.get("entity_name")
            or parent_base
        )
        child_table.setdefault("columns", []).append(
            _template_column(
                child_column,
                f"{logical_parent} 일련번호",
                constraints=["FK"],
                nullable=False,
            )
        )
    else:
        for column in child_table.get("columns", []):
            if not isinstance(column, dict):
                continue
            if str(column.get("physical_name") or column.get("column_name") or "") == child_column:
                constraints = [
                    str(item) for item in column.get("constraints", []) if str(item)
                ]
                if "FK" not in {item.upper() for item in constraints}:
                    constraints.append("FK")
                column["constraints"] = constraints
                column["fk"] = "Y"
                break
    return child_column


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
        "tbl_model_ai": "AI 모델",
        "tbl_rag": "RAG 지식베이스",
        "tbl_job": "작업",
        "tbl_user": "사용자",
        "tbl_document": "문서",
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
