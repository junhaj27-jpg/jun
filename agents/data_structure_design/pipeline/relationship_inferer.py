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
    relationships: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for table in tables:
        for column in table.get("columns", []):
            column_name = str(column.get("column_name") or "")
            if column_name not in pk_owner:
                continue
            parent_table = pk_owner[column_name]
            child_table = table["table_name"]
            if parent_table == child_table:
                continue
            key = (parent_table, column_name, child_table, column_name)
            if key in seen or parent_table not in by_table:
                continue
            seen.add(key)
            relationships.append(
                {
                    "relationship_id": f"REL-{len(relationships) + 1:03d}",
                    "from_table": child_table,
                    "from_column": column_name,
                    "to_table": parent_table,
                    "to_column": column_name,
                    "parent_table": parent_table,
                    "parent_column": column_name,
                    "child_table": child_table,
                    "child_column": column_name,
                    "relationship_type": "N:1",
                    "description": f"{child_table}는 {parent_table}를 참조한다.",
                }
            )
    return relationships


def _pk_column(table: dict[str, Any]) -> str:
    for column in table.get("columns", []):
        if column.get("pk") is True or "PK" in column.get("constraints", []):
            return str(column.get("column_name") or column.get("physical_name") or "")
    return ""
