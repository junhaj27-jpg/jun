"""최종 ERD JSON의 표현과 관계 정합성을 보정하고 검증합니다."""

from copy import deepcopy
import re
from typing import Any

from agents.data_structure_design.pipeline.relationship_inferer import infer_relationships


MAX_ENTITY_NAME_LENGTH = 24
GENERIC_ENTITY_NAMES = {"엔티티", "entity", "table", "테이블", "데이터", "정보", "객체", "항목", "관리", "업무"}


def prepare_erd_quality(document: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """안전한 표현/키 보정 후 의미 변경이 필요한 문제를 보고합니다."""

    result = deepcopy(document)
    tables = [table for table in result.get("tables", []) if isinstance(table, dict)]
    relationships = [relation for relation in result.get("relationships", []) if isinstance(relation, dict)]
    corrections: list[dict[str, Any]] = []

    for table in tables:
        for column in table.get("columns", []):
            if isinstance(column, dict):
                _normalize_column_flags(table, column, corrections)
        _ensure_primary_key(table, corrections)

    relationships = _complete_inferable_relationships(tables, relationships, corrections)
    _synchronize_relationship_flags(tables, relationships, corrections)
    result["tables"] = tables
    result["relationships"] = relationships
    report = inspect_erd_quality(result)
    report["corrections"] = corrections
    return result, report


def ensure_primary_keys(
    document: dict[str, Any],
    target_scopes: list[str] | set[str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """PK가 없는 대상 테이블만 규칙 기반으로 보정합니다."""

    result = deepcopy(document)
    corrections: list[dict[str, Any]] = []
    targets = {str(value) for value in (target_scopes or []) if str(value)}
    for table in result.get("tables", []):
        if not isinstance(table, dict):
            continue
        scope_values = {
            str(table.get("table_id") or ""),
            str(table.get("entity_id") or ""),
            _table_name(table),
        }
        if targets and not (targets & scope_values):
            continue
        for column in table.get("columns", []):
            if isinstance(column, dict):
                _normalize_column_flags(table, column, corrections)
        _ensure_primary_key(table, corrections)
    return result, corrections


def inspect_erd_quality(document: dict[str, Any]) -> dict[str, Any]:
    tables = [table for table in document.get("tables", []) if isinstance(table, dict)]
    relationships = [relation for relation in document.get("relationships", []) if isinstance(relation, dict)]
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    table_by_name = {_table_name(table): table for table in tables if _table_name(table)}

    _inspect_entity_names(tables, errors)
    _inspect_semantic_duplicates(tables, errors)
    _inspect_relation_consistency(table_by_name, relationships, errors)
    _inspect_unmapped_fk_columns(table_by_name, relationships, errors)
    _inspect_common_column_overuse(tables, warnings)
    _inspect_standalone_entities(tables, relationships, warnings)

    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "corrections": [],
    }


def entity_name_needs_llm_review(value: Any) -> bool:
    text = str(value or "").strip()
    normalized = text.lower()
    if not text or normalized in GENERIC_ENTITY_NAMES:
        return True
    if text.lower().startswith("tbl_") or re.fullmatch(r"TABLE-\d+", text, re.IGNORECASE):
        return True
    if len(text) > MAX_ENTITY_NAME_LENGTH or "_" in text or "\n" in text:
        return True
    return bool(
        re.search(
            r"(?:합니다|됩니다|한다|된다|하여야|해야\s*함|기능|요구사항|기본사항|정보를\s*관리)",
            text,
        )
    )


def _normalize_column_flags(
    table: dict[str, Any],
    column: dict[str, Any],
    corrections: list[dict[str, Any]],
) -> None:
    constraints = [str(value) for value in column.get("constraints", []) if str(value)]
    upper = {value.upper() for value in constraints}
    pk = _flag(column.get("pk")) or _flag(column.get("is_pk")) or "PK" in upper or "PRIMARY KEY" in upper
    fk = _flag(column.get("fk")) or _flag(column.get("is_fk")) or "FK" in upper or "FOREIGN KEY" in upper
    idx = (
        _flag(column.get("idx"))
        or _flag(column.get("inx"))
        or _flag(column.get("is_idx"))
        or pk
        or fk
        or bool(upper & {"INDEX", "IDX"})
    )
    expected = {
        "pk": "Y" if pk else "",
        "fk": "Y" if fk else "",
        "idx": "Y" if idx else "",
        "inx": "Y" if idx else "",
    }
    before = {key: column.get(key) for key in ("pk", "fk", "idx", "inx", "is_pk", "is_fk", "is_idx")}
    changed = any(column.get(key) != value for key, value in expected.items()) or any(
        key in column for key in ("is_pk", "is_fk", "is_idx")
    )
    column["pk"] = "Y" if pk else ""
    column["fk"] = "Y" if fk else ""
    column["idx"] = "Y" if idx else ""
    column["inx"] = "Y" if idx else ""
    column.pop("is_pk", None)
    column.pop("is_fk", None)
    column.pop("is_idx", None)
    if pk and "PK" not in upper:
        constraints.append("PK")
    if fk and "FK" not in upper:
        constraints.append("FK")
    column["constraints"] = list(dict.fromkeys(constraints))
    after = {key: column.get(key) for key in ("pk", "fk", "idx", "inx")}
    if changed:
        corrections.append(
            {
                "type": "KEY_FLAG_NORMALIZED",
                "target": f"{_table_name(table)}.{_column_name(column)}",
                "before": before,
                "after": after,
            }
        )


def _ensure_primary_key(
    table: dict[str, Any],
    corrections: list[dict[str, Any]],
) -> None:
    columns = [
        column
        for column in table.get("columns", [])
        if isinstance(column, dict)
    ]
    if not columns or any(_is_key(column, "PK") for column in columns):
        return

    ranked = sorted(
        (
            (_primary_key_candidate_score(column, index), -index, column)
            for index, column in enumerate(columns)
        ),
        key=lambda item: (item[0], item[1]),
        reverse=True,
    )
    score, _, candidate = ranked[0]
    if score < 70:
        return

    candidate["nullable"] = False
    _set_key_flag(candidate, "PK")
    corrections.append(
        {
            "type": "PRIMARY_KEY_INFERRED",
            "target": f"{_table_name(table)}.{_column_name(candidate)}",
        }
    )


def _primary_key_candidate_score(column: dict[str, Any], index: int) -> int:
    name = _column_name(column).lower()
    logical_name = str(
        column.get("attribute_name")
        or column.get("logical_name")
        or ""
    ).lower()
    score = 0
    if column.get("nullable") is False:
        score += 30
    if name.endswith("_sn"):
        score += 100
    elif name.endswith("_mng_no"):
        score += 95
    elif name.endswith("_id"):
        score += 90
    elif name.endswith("_no"):
        score += 80
    elif re.search(r"(?:일련번호|관리번호|식별자|아이디|id)$", logical_name):
        score += 75
    if index == 0:
        score += 10
    if str(column.get("data_type") or "").upper() in {
        "BIGINT",
        "INTEGER",
        "INT",
        "NUMERIC",
        "VARCHAR",
        "CHAR",
    }:
        score += 10
    return score


def _complete_inferable_relationships(
    tables: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    corrections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result = [_normalize_relationship(relation) for relation in relationships]
    inferred = infer_relationships(tables)
    existing = {_relationship_key(relation) for relation in result}
    for relation in inferred:
        normalized = _normalize_relationship(relation)
        same_pair = next(
            (
                current
                for current in result
                if current.get("parent_table") == normalized.get("parent_table")
                and current.get("child_table") == normalized.get("child_table")
            ),
            None,
        )
        if same_pair is not None and (
            not same_pair.get("parent_column") or not same_pair.get("child_column")
        ):
            same_pair["parent_column"] = normalized.get("parent_column")
            same_pair["to_column"] = normalized.get("parent_column")
            same_pair["child_column"] = normalized.get("child_column")
            same_pair["from_column"] = normalized.get("child_column")
            corrections.append(
                {
                    "type": "RELATIONSHIP_COLUMNS_INFERRED",
                    "target": str(same_pair.get("relationship_id") or _relationship_key(same_pair)),
                }
            )
            existing.add(_relationship_key(same_pair))
            continue
        key = _relationship_key(normalized)
        if key in existing:
            continue
        result.append(normalized)
        existing.add(key)
        corrections.append({"type": "RELATIONSHIP_INFERRED", "target": ".".join(key)})
    return result


def _synchronize_relationship_flags(
    tables: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    corrections: list[dict[str, Any]],
) -> None:
    table_by_name = {_table_name(table): table for table in tables if _table_name(table)}
    for relation in relationships:
        parent = table_by_name.get(str(relation.get("parent_table") or ""))
        child = table_by_name.get(str(relation.get("child_table") or ""))
        if parent is None or child is None:
            continue
        parent_column = _find_column(parent, relation.get("parent_column")) or _single_pk(parent)
        child_column = _find_column(child, relation.get("child_column"))
        if child_column is None and parent_column is not None:
            child_column = _infer_child_column(parent, child, parent_column)
        if parent_column is None or child_column is None:
            continue
        before = {
            "parent_column": relation.get("parent_column"),
            "child_column": relation.get("child_column"),
            "parent_entity_name": relation.get("parent_entity_name"),
            "child_entity_name": relation.get("child_entity_name"),
        }
        relation["parent_column"] = _column_name(parent_column)
        relation["to_column"] = _column_name(parent_column)
        relation["child_column"] = _column_name(child_column)
        relation["from_column"] = _column_name(child_column)
        relation["parent_entity_name"] = _entity_name(parent)
        relation["child_entity_name"] = _entity_name(child)
        parent_key_changed = _set_key_flag(parent_column, "PK")
        child_key_changed = _set_key_flag(child_column, "FK")
        key_changed = parent_key_changed or child_key_changed
        after = {
            "parent_column": relation.get("parent_column"),
            "child_column": relation.get("child_column"),
            "parent_entity_name": relation.get("parent_entity_name"),
            "child_entity_name": relation.get("child_entity_name"),
        }
        if before != after or key_changed:
            corrections.append(
                {
                    "type": "RELATION_KEY_FLAGS_SYNCHRONIZED",
                    "target": str(relation.get("relationship_id") or _relationship_key(relation)),
                }
            )


def _inspect_entity_names(tables: list[dict[str, Any]], errors: list[dict[str, Any]]) -> None:
    for table in tables:
        name = _entity_name(table)
        scope = str(table.get("entity_id") or table.get("table_id") or _table_name(table))
        if not name:
            errors.append(_issue("ENTITY_NAME_MISSING", scope, "엔티티명이 없습니다."))
        elif len(name) > MAX_ENTITY_NAME_LENGTH:
            errors.append(_issue("ENTITY_NAME_OVERLONG", scope, "엔티티명이 너무 깁니다."))
        elif entity_name_needs_llm_review(name):
            errors.append(_issue("ENTITY_NAME_SENTENCE", scope, "요구사항 문장 또는 카테고리가 엔티티명으로 사용되었습니다."))


def _inspect_semantic_duplicates(tables: list[dict[str, Any]], errors: list[dict[str, Any]]) -> None:
    by_key: dict[str, list[str]] = {}
    for table in tables:
        name_key = re.sub(r"[\s_-]+", "", _entity_name(table)).lower()
        role_key = _structural_role(table)
        key = f"{name_key}:{role_key}" if name_key else ""
        if key:
            by_key.setdefault(key, []).append(str(table.get("entity_id") or _table_name(table)))
    for scopes in by_key.values():
        if len(scopes) > 1:
            errors.append(_issue("ENTITY_SEMANTIC_DUPLICATED", scopes, "동일한 논리 엔티티명이 중복되었습니다."))
    for table in tables:
        duplicate_of = str(table.get("semantic_duplicate_of") or "").strip()
        if duplicate_of:
            errors.append(
                _issue(
                    "ENTITY_SEMANTIC_DUPLICATED",
                    [str(table.get("entity_id") or _table_name(table)), duplicate_of],
                    "LLM 카탈로그 검토에서 의미 중복 엔티티로 판정되었습니다.",
                )
            )


def _structural_role(table: dict[str, Any]) -> str:
    explicit = str(table.get("table_type") or "").strip().upper()
    if explicit:
        return explicit
    text = " ".join(
        [
            _table_name(table),
            _entity_name(table),
            str(table.get("entity_description") or table.get("description") or ""),
        ]
    ).lower()
    role_patterns = (
        ("JOB_STEP", r"(?:job[_\s-]?step|작업\s*단계)"),
        ("VERSION", r"(?:version|ver(?:sion)?|버전)"),
        ("HISTORY", r"(?:history|hist|이력)"),
        ("LOG", r"(?:log|로그)"),
        ("MAPPING", r"(?:mapping|map|매핑|연결)"),
        ("DETAIL", r"(?:detail|상세|detail_item)"),
        ("CONFIG", r"(?:config|setting|설정)"),
        ("FILE", r"(?:file|파일|첨부)"),
        ("APPROVAL", r"(?:approval|approve|승인|결재)"),
        ("JOB", r"(?:job|task|작업)"),
        ("CODE", r"(?:code|코드)"),
    )
    for role, pattern in role_patterns:
        if re.search(pattern, text):
            return role
    return "MASTER"


def _inspect_relation_consistency(
    table_by_name: dict[str, dict[str, Any]],
    relationships: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    for relation in relationships:
        scope = str(relation.get("relationship_id") or _relationship_key(relation))
        parent = table_by_name.get(str(relation.get("parent_table") or ""))
        child = table_by_name.get(str(relation.get("child_table") or ""))
        if parent is None or child is None:
            errors.append(_issue("RELATION_TABLE_MISSING", scope, "관계 대상 엔티티가 없습니다."))
            continue
        parent_column = _find_column(parent, relation.get("parent_column"))
        child_column = _find_column(child, relation.get("child_column"))
        if parent_column is None or child_column is None:
            errors.append(_issue("RELATION_COLUMN_MISSING", scope, "관계의 PK/FK 컬럼이 없습니다."))
            continue
        if not _is_key(parent_column, "PK") or not _is_key(child_column, "FK"):
            errors.append(_issue("RELATION_KEY_MISMATCH", scope, "관계의 부모 PK 또는 자식 FK 표시가 일치하지 않습니다."))


def _inspect_unmapped_fk_columns(
    table_by_name: dict[str, dict[str, Any]],
    relationships: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    mapped = {
        (str(relation.get("child_table") or ""), str(relation.get("child_column") or ""))
        for relation in relationships
    }
    for table_name, table in table_by_name.items():
        for column in table.get("columns", []):
            if isinstance(column, dict) and _is_key(column, "FK") and (table_name, _column_name(column)) not in mapped:
                errors.append(
                    _issue(
                        "FK_RELATION_MISSING",
                        f"{table_name}.{_column_name(column)}",
                        "FK 컬럼에 대응하는 관계가 없습니다.",
                    )
                )


def _inspect_common_column_overuse(tables: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> None:
    for table in tables:
        columns = [column for column in table.get("columns", []) if isinstance(column, dict)]
        business_columns = [column for column in columns if not _is_common_column(column) and not _is_key(column, "PK")]
        table_base = _table_name(table).removeprefix("tbl_")
        skeleton_names = {
            f"{table_base}_sn",
            f"{table_base}_id",
            f"{table_base}_nm",
            f"{table_base}_cn",
            f"{table_base}_stts_cd",
            f"{table_base}_status_cd",
            "use_yn",
            "del_yn",
            "reg_dt",
            "crt_dt",
            "mdfcn_dt",
            "udt_dt",
        }
        only_generic_skeleton = bool(columns) and all(_column_name(column) in skeleton_names for column in columns)
        if len(columns) >= 5 and (not business_columns or only_generic_skeleton):
            warnings.append(
                _issue(
                    "COMMON_COLUMN_OVERUSE",
                    str(table.get("entity_id") or _table_name(table)),
                    "업무 속성 없이 공통 컬럼만 구성되어 있습니다.",
                )
            )


def _inspect_standalone_entities(
    tables: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    related = {
        str(value)
        for relation in relationships
        for value in (relation.get("parent_table"), relation.get("child_table"))
        if value
    }
    standalone = [_table_name(table) for table in tables if _table_name(table) not in related]
    if len(standalone) >= 4 and len(standalone) * 2 > len(tables):
        warnings.append(_issue("STANDALONE_ENTITY_EXCESSIVE", standalone, "단독 엔티티 비율이 높아 관계 누락 검토가 필요합니다."))


def _normalize_relationship(relation: dict[str, Any]) -> dict[str, Any]:
    result = dict(relation)
    result["parent_table"] = str(result.get("parent_table") or result.get("to_table") or result.get("to") or "")
    result["child_table"] = str(result.get("child_table") or result.get("from_table") or result.get("from") or "")
    result["parent_column"] = str(result.get("parent_column") or result.get("to_column") or "")
    result["child_column"] = str(result.get("child_column") or result.get("from_column") or "")
    result["to_table"] = result["parent_table"]
    result["from_table"] = result["child_table"]
    result["to_column"] = result["parent_column"]
    result["from_column"] = result["child_column"]
    return result


def _set_key_flag(column: dict[str, Any], marker: str) -> bool:
    before = (list(column.get("constraints", [])), column.get(marker.lower()), column.get("idx"), column.get("inx"))
    constraints = [str(value) for value in column.get("constraints", []) if str(value)]
    if marker not in {value.upper() for value in constraints}:
        constraints.append(marker)
    column["constraints"] = constraints
    key = marker.lower()
    column[key] = "Y"
    column["idx"] = "Y"
    column["inx"] = "Y"
    after = (list(column.get("constraints", [])), column.get(marker.lower()), column.get("idx"), column.get("inx"))
    return before != after


def _is_key(column: dict[str, Any], marker: str) -> bool:
    return _flag(column.get(marker.lower())) or marker in {str(value).upper() for value in column.get("constraints", [])}


def _flag(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().upper() in {"Y", "YES", "TRUE", "1", "PK", "FK", "IDX", "INDEX"}
    return bool(value)


def _single_pk(table: dict[str, Any]) -> dict[str, Any] | None:
    values = [column for column in table.get("columns", []) if isinstance(column, dict) and _is_key(column, "PK")]
    return values[0] if len(values) == 1 else None


def _find_column(table: dict[str, Any], value: Any) -> dict[str, Any] | None:
    name = str(value or "")
    if not name:
        return None
    return next((column for column in table.get("columns", []) if isinstance(column, dict) and _column_name(column) == name), None)


def _infer_child_column(
    parent: dict[str, Any],
    child: dict[str, Any],
    parent_column: dict[str, Any],
) -> dict[str, Any] | None:
    parent_name = _column_name(parent_column)
    exact = [
        column
        for column in child.get("columns", [])
        if isinstance(column, dict) and _column_name(column) == parent_name
    ]
    if len(exact) == 1:
        return exact[0]
    parent_stem = _table_name(parent).removeprefix("tbl_")
    candidates = [
        column
        for column in child.get("columns", [])
        if isinstance(column, dict)
        and _column_name(column).removesuffix("_sn").removesuffix("_id") == parent_stem
    ]
    return candidates[0] if len(candidates) == 1 else None


def _relationship_key(relation: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(relation.get("parent_table") or ""),
        str(relation.get("parent_column") or ""),
        str(relation.get("child_table") or ""),
        str(relation.get("child_column") or ""),
    )


def _table_name(table: dict[str, Any]) -> str:
    return str(table.get("table_name") or table.get("physical_name") or "")


def _entity_name(table: dict[str, Any]) -> str:
    return str(table.get("entity_name") or table.get("logical_name") or "").strip()


def _column_name(column: dict[str, Any]) -> str:
    return str(column.get("column_name") or column.get("physical_name") or "")


def _is_common_column(column: dict[str, Any]) -> bool:
    name = _column_name(column).lower()
    return bool(re.search(r"(?:crt|reg|create|created|udt|upd|update|modified|del|use)_(?:dt|at|yn|sn)$", name))


def _issue(code: str, scope: Any, message: str) -> dict[str, Any]:
    target_scope = scope if isinstance(scope, list) else [str(scope)]
    return {"code": code, "message": message, "target_scope": target_scope}
