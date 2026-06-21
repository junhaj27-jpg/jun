"""최종 테이블 목록에서 PK/FK 관계를 추론합니다."""

from typing import Any


def infer_relationships(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_table = {table["table_name"]: table for table in tables}
    pk_by_table = {
        table["table_name"]: _pk_column(table)
        for table in tables
    }
    pk_owner = {
        pk: table_name
        for table_name, pk in pk_by_table.items()
        if pk
    }
    alias_owner = _alias_owner_map(tables)
    relationships: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for table in tables:
        for column in table.get("columns", []):
            column_name = str(column.get("column_name") or "")
            parent_table = pk_owner.get(column_name)
            if parent_table is None and _looks_like_fk(column):
                parent_table = alias_owner.get(_identifier_stem(column_name))
            if parent_table is None:
                continue
            child_table = table["table_name"]
            if parent_table == child_table:
                continue
            parent_column = pk_by_table.get(parent_table) or column_name
            key = (parent_table, parent_column, child_table, column_name)
            if key in seen or parent_table not in by_table:
                continue
            seen.add(key)
            relationships.append(
                {
                    "relationship_id": f"REL-{len(relationships) + 1:03d}",
                    "from_table": child_table,
                    "from_column": column_name,
                    "to_table": parent_table,
                    "to_column": parent_column,
                    "parent_table": parent_table,
                    "parent_column": parent_column,
                    "child_table": child_table,
                    "child_column": column_name,
                    "relationship_type": "N:1",
                    "description": f"{child_table}는 {parent_table}를 참조한다.",
                }
            )
    return relationships


_IDENTIFIER_ALIASES = {
    "organization": "org",
    "organisation": "org",
    "department": "dept",
    "document": "docs",
    "doc": "docs",
}


def _alias_owner_map(tables: list[dict[str, Any]]) -> dict[str, str]:
    candidates: dict[str, list[str]] = {}
    for table in tables:
        table_name = str(table.get("table_name") or "")
        base = table_name.removeprefix("tbl_")
        aliases = {base, _canonical_identifier(base)}
        for alias, canonical in _IDENTIFIER_ALIASES.items():
            if canonical in aliases:
                aliases.add(alias)
        for alias in aliases:
            candidates.setdefault(alias, []).append(table_name)
    return {
        alias: owners[0]
        for alias, owners in candidates.items()
        if len(set(owners)) == 1
    }


def _looks_like_fk(column: dict[str, Any]) -> bool:
    name = str(column.get("column_name") or column.get("physical_name") or "")
    constraints = {str(item).upper() for item in column.get("constraints") or []}
    return bool(column.get("fk") or "FK" in constraints or name.endswith(("_sn", "_id")))


def _identifier_stem(value: str) -> str:
    stem = str(value or "").lower()
    for suffix in ("_sn", "_id"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return _canonical_identifier(stem)


def _canonical_identifier(value: str) -> str:
    return _IDENTIFIER_ALIASES.get(value, value)


def _pk_column(table: dict[str, Any]) -> str:
    for column in table.get("columns", []):
        if column.get("pk") is True or "PK" in column.get("constraints", []):
            return str(column.get("column_name") or column.get("physical_name") or "")
    return ""
