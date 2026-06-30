"""요구사항 기반 ERD JSON을 검증합니다."""

from typing import Any


def validate_erd(tables: list[dict[str, Any]], relationships: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    table_names = {table["table_name"] for table in tables}
    columns_by_table = {
        table["table_name"]: {column["column_name"] for column in table.get("columns", [])}
        for table in tables
    }

    for table in tables:
        if not any(column.get("pk") is True or "PK" in column.get("constraints", []) for column in table.get("columns", [])):
            errors.append({"type": "PK_MISSING", "message": "PK 컬럼이 없습니다.", "target_table": table["table_name"]})
        if not table.get("source_requirement_ids"):
            errors.append({"type": "SOURCE_REQUIREMENT_MISSING", "message": "source_requirement_ids가 없습니다.", "target_table": table["table_name"]})

    for relationship in relationships:
        to_table = relationship.get("to_table") or relationship.get("parent_table")
        to_column = relationship.get("to_column") or relationship.get("parent_column")
        from_table = relationship.get("from_table") or relationship.get("child_table")
        from_column = relationship.get("from_column") or relationship.get("child_column")
        if to_table not in table_names or from_table not in table_names:
            errors.append({"type": "FK_TARGET_TABLE_MISSING", "message": "FK 대상 테이블이 없습니다.", "relationship": relationship})
            continue
        if to_column not in columns_by_table.get(to_table, set()) or from_column not in columns_by_table.get(from_table, set()):
            errors.append({"type": "FK_TARGET_COLUMN_MISSING", "message": "FK 대상 컬럼이 없습니다.", "relationship": relationship})

    duplicate_groups = _possible_duplicates(tables)
    for group in duplicate_groups:
        warnings.append(
            {
                "type": "POSSIBLE_DUPLICATE_TABLE",
                "message": f"{', '.join(group)}의 의미가 유사합니다.",
                "target_tables": group,
            }
        )

    return {"is_valid": not errors, "errors": errors, "warnings": warnings}


def _possible_duplicates(tables: list[dict[str, Any]]) -> list[list[str]]:
    by_korean: dict[str, list[str]] = {}
    for table in tables:
        key = str(table.get("table_korean_name") or "").replace("정보", "").strip()
        if not key:
            continue
        by_korean.setdefault(key, []).append(table["table_name"])
    return [names for names in by_korean.values() if len(names) > 1]
