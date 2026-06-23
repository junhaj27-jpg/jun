"""DB 설계 JSON의 테이블/테이블스페이스 식별자를 보정하고 검증합니다."""

from copy import deepcopy
from difflib import SequenceMatcher
import re
from typing import Any


TABLE_PATTERN = re.compile(r"^tbl_[a-z0-9]+(?:_[a-z0-9]+)*$")
TABLESPACE_PATTERN = re.compile(r"^TS_[A-Z0-9]+(?:_[A-Z0-9]+)*$")
FORBIDDEN_IDENTIFIER_TOKEN = re.compile(r"(?:^|_)(?:unresolved|unknown|temp|temporary|hash|uuid)(?:_|$)", re.IGNORECASE)
HASH_SUFFIX = re.compile(r"_[0-9a-f]{8,}$", re.IGNORECASE)
UUID_VALUE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", re.IGNORECASE)
GENERIC_TABLE_IDENTIFIERS = {
    "tbl_entity",
    "tbl_table",
    "tbl_data",
    "tbl_info",
    "tbl_information",
    "tbl_object",
    "tbl_item",
}


def prepare_db_quality(document: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    result = deepcopy(document)
    tables = [table for table in result.get("tables", []) if isinstance(table, dict)]
    corrections: list[dict[str, Any]] = []
    for table in tables:
        table_name = _resolved_table_name(table)
        if valid_table_identifier(table_name):
            if table.get("table_name") != table_name:
                corrections.append(
                    {
                        "type": "DB_TABLE_NAME_SYNCHRONIZED",
                        "target": table_name,
                        "before": table.get("table_name"),
                        "after": table_name,
                    }
                )
                table["table_name"] = table_name
            table["physical_name"] = table_name
            if table.get("table_id") != table_name:
                corrections.append(
                    {
                        "type": "DB_TABLE_ID_SYNCHRONIZED",
                        "target": table_name,
                        "before": table.get("table_id"),
                        "after": table_name,
                    }
                )
                table["table_id"] = table_name
            tablespace = tablespace_name(table_name)
            if table.get("tablespace_name") != tablespace:
                corrections.append(
                    {
                        "type": "DB_TABLESPACE_SYNCHRONIZED",
                        "target": table_name,
                        "before": table.get("tablespace_name"),
                        "after": tablespace,
                    }
                )
                table["tablespace_name"] = tablespace
    result["tables"] = tables
    report = inspect_db_quality(result)
    report["corrections"] = corrections
    return result, report


def inspect_db_quality(document: dict[str, Any]) -> dict[str, Any]:
    tables = [table for table in document.get("tables", []) if isinstance(table, dict)]
    errors: list[dict[str, Any]] = []
    by_table_name: dict[str, list[str]] = {}
    by_logical_name: dict[str, list[str]] = {}
    for table in tables:
        table_name = _resolved_table_name(table)
        table_id = str(table.get("table_id") or "").strip()
        tablespace = str(table.get("tablespace_name") or "").strip()
        logical_name = str(
            table.get("entity_name")
            or table.get("table_logical_name")
            or table.get("logical_name")
            or ""
        ).strip()
        scope = table_name or table_id or logical_name or "table"
        if not valid_table_identifier(table_name):
            errors.append(_issue("DB_TABLE_ID_UNRESOLVED", scope, "의미 있는 tbl_ snake_case 테이블명을 결정하지 못했습니다."))
        if table_id != table_name:
            errors.append(_issue("DB_TABLE_ID_MAPPING_INVALID", scope, "table_id와 table_name이 일치하지 않습니다."))
        if not valid_tablespace_identifier(tablespace):
            errors.append(_issue("DB_TABLESPACE_ID_INVALID", scope, "TS ID 형식이 올바르지 않습니다."))
        elif valid_table_identifier(table_name) and tablespace != tablespace_name(table_name):
            errors.append(_issue("DB_TABLESPACE_MAPPING_INVALID", scope, "TS ID가 테이블 ID 기준으로 생성되지 않았습니다."))
        if not logical_name:
            errors.append(_issue("DB_TABLE_ENTITY_MAPPING_INVALID", scope, "테이블에 대응하는 논리 엔티티명이 없습니다."))
        elif _english_entity_mapping_mismatch(logical_name, table_name):
            errors.append(_issue("DB_TABLE_ENTITY_MAPPING_INVALID", scope, "영문 논리 엔티티명과 물리 테이블명의 핵심 용어가 다릅니다."))
        by_table_name.setdefault(table_name, []).append(scope)
        semantic_key = re.sub(r"[\s_-]+", "", logical_name).lower()
        if semantic_key:
            by_logical_name.setdefault(semantic_key, []).append(scope)

    for table_name, scopes in by_table_name.items():
        if table_name and len(scopes) > 1:
            errors.append(_issue("DB_TABLE_NAME_DUPLICATED", scopes, "동일한 테이블명이 중복되었습니다."))
    for scopes in by_logical_name.values():
        if len(scopes) > 1:
            errors.append(_issue("DB_TABLE_SEMANTIC_DUPLICATED", scopes, "동일한 논리 테이블이 중복되었습니다."))
    similar_scopes: set[tuple[str, str]] = set()
    named_tables = []
    for table in tables:
        resolved_name = _resolved_table_name(table)
        if valid_table_identifier(resolved_name):
            named_tables.append((resolved_name.removeprefix("tbl_"), resolved_name))
    for index, (left_name, left_scope) in enumerate(named_tables):
        for right_name, right_scope in named_tables[index + 1 :]:
            if left_name != right_name and SequenceMatcher(None, left_name, right_name).ratio() >= 0.9:
                similar_scopes.add(tuple(sorted((left_scope, right_scope))))
    for scopes in sorted(similar_scopes):
        errors.append(_issue("DB_TABLE_SEMANTIC_DUPLICATED", list(scopes), "유사한 물리 테이블명이 중복 후보로 확인되었습니다."))
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": [],
        "corrections": [],
    }


def valid_table_identifier(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(
        TABLE_PATTERN.fullmatch(text)
        and text not in GENERIC_TABLE_IDENTIFIERS
        and not FORBIDDEN_IDENTIFIER_TOKEN.search(text)
        and not HASH_SUFFIX.search(text)
        and not UUID_VALUE.search(text)
    )


def valid_tablespace_identifier(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(
        TABLESPACE_PATTERN.fullmatch(text)
        and not FORBIDDEN_IDENTIFIER_TOKEN.search(text)
        and not HASH_SUFFIX.search(text)
        and not UUID_VALUE.search(text)
    )


def tablespace_name(table_name: str) -> str:
    return f"TS_{str(table_name).removeprefix('tbl_').upper()}"


def _resolved_table_name(table: dict[str, Any]) -> str:
    return next(
        (
            str(value).strip()
            for value in (table.get("table_name"), table.get("physical_name"), table.get("table_id"))
            if valid_table_identifier(value)
        ),
        str(table.get("table_name") or table.get("physical_name") or "").strip(),
    )


def _english_entity_mapping_mismatch(logical_name: str, table_name: str) -> bool:
    if not valid_table_identifier(table_name) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9 _-]*", logical_name):
        return False
    logical_tokens = {
        token.lower()
        for token in re.findall(r"[A-Za-z0-9]+", logical_name)
        if token.lower() not in {"table", "entity", "data", "information"}
    }
    physical_tokens = set(table_name.removeprefix("tbl_").split("_"))
    return bool(logical_tokens and not logical_tokens.intersection(physical_tokens))


def _issue(code: str, scope: Any, message: str) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "target_scope": scope if isinstance(scope, list) else [str(scope)],
    }
