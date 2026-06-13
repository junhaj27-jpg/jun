# ERD 구조를 Mermaid 코드로 생성합니다.

from typing import Any


def build_erd_mermaid(structure: dict[str, Any]) -> str:
    entities = structure.get("entities") or structure.get("tables") or []
    relationships = structure.get("relationships") or structure.get("relations") or []
    lines = ["erDiagram"]
    for entity in entities:
        name = str(entity.get("name") or entity.get("physical_name") or entity.get("table_name") or "")
        if not name:
            continue
        lines.append(f"    {name} {{")
        for column in entity.get("columns") or []:
            data_type = str(column.get("data_type") or "VARCHAR").replace(" ", "_")
            column_name = str(column.get("physical_name") or column.get("column_name") or "column")
            constraints = column.get("constraints") or []
            marker = " PK" if "PK" in constraints else (" FK" if "FK" in constraints else "")
            lines.append(f"        {data_type} {column_name}{marker}")
        lines.append("    }")
    for relation in relationships:
        parent = relation.get("parent_table") or relation.get("from") or relation.get("source")
        child = relation.get("child_table") or relation.get("to") or relation.get("target")
        if parent and child:
            lines.append(f"    {parent} ||--o{{ {child} : relates")
    return "\n".join(lines)
