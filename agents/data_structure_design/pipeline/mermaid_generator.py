"""최종 ERD JSON에서 Mermaid 입력 구조를 생성합니다."""

from typing import Any


def build_mermaid_structure(erd_schema: dict[str, Any]) -> dict[str, Any]:
    tables = erd_schema.get("tables") if isinstance(erd_schema.get("tables"), list) else []
    mermaid_tables = [
        {
            "entity_name": table.get("entity_name") or table.get("logical_name") or table.get("table_korean_name"),
            "table_name": table.get("table_name"),
            "physical_name": table.get("table_name"),
            "name": table.get("table_name"),
            "logical_name": table.get("table_korean_name"),
            "domain_group": table.get("domain_group", ""),
            "importance_score": table.get("importance_score", 0),
            "relation_count": table.get("relation_count", 0),
            "columns": [
                {
                    "attribute_name": column.get("attribute_name") or column.get("logical_name"),
                    "column_name": column.get("column_name"),
                    "physical_name": column.get("column_name"),
                    "data_type": column.get("data_type"),
                    "constraints": _constraints(column),
                }
                for column in table.get("columns", [])
                if isinstance(column, dict)
            ],
        }
        for table in tables
        if isinstance(table, dict)
    ]
    return {
        "tables": mermaid_tables,
        "entities": mermaid_tables,
        "relationships": erd_schema.get("relationships") or [],
    }


def _constraints(column: dict[str, Any]) -> list[str]:
    values = list(column.get("constraints") or [])
    if column.get("pk") and "PK" not in values:
        values.append("PK")
    if column.get("fk") and "FK" not in values:
        values.append("FK")
    return values
