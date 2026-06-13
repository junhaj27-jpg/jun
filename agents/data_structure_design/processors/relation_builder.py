# 테이블 간 PK 및 FK 관계를 설계합니다.

from typing import Any


def build_relationships(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    relationships = []
    if len(tables) < 2:
        return relationships
    parent = tables[0]
    parent_pk = next(
        (column for column in parent["columns"] if "PK" in column.get("constraints", [])),
        None,
    )
    if parent_pk is None:
        return relationships
    for index, child in enumerate(tables[1:], start=1):
        relationships.append(
            {
                "relationship_id": f"REL-{index:03d}",
                "parent_table": parent["physical_name"],
                "parent_column": parent_pk["physical_name"],
                "child_table": child["physical_name"],
                "relationship_type": "1:N",
            }
        )
    return relationships
