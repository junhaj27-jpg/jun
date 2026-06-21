# ERD 구조를 Mermaid 코드로 생성합니다.

import re
from collections import defaultdict
from typing import Any


def build_erd_mermaid(
    structure: dict[str, Any],
    *,
    include_columns: bool = True,
    core_columns_only: bool = False,
    max_columns: int = 6,
) -> str:
    entities = structure.get("entities") or structure.get("tables") or []
    relationships = structure.get("relationships") or structure.get("relations") or []
    entity_identifier_by_physical = _entity_identifier_map(entities)
    lines = ["erDiagram"]
    for entity in entities:
        name = str(
            entity.get("entity_name")
            or entity.get("logical_name")
            or entity.get("name")
            or entity.get("physical_name")
            or entity.get("table_name")
            or ""
        )
        if not name:
            continue
        table_name = _entity_identifier(entity)
        lines.append(f"    {table_name} {{")
        columns = entity.get("columns") or []
        if not include_columns:
            columns = []
        elif core_columns_only:
            columns = _core_columns(columns, max_columns=max_columns)
        for column in columns:
            data_type = _data_type(str(column.get("data_type") or "VARCHAR"))
            column_name = _identifier(
                str(
                    column.get("attribute_name")
                    or column.get("logical_name")
                    or column.get("column_logical_name")
                    or column.get("physical_name")
                    or column.get("column_name")
                    or "column"
                )
            )
            constraints = column.get("constraints") or []
            marker = " PK" if "PK" in constraints else (" FK" if "FK" in constraints else "")
            lines.append(f"        {data_type} {column_name}{marker}")
        lines.append("    }")
    for relation in relationships:
        parent = relation.get("parent_table") or relation.get("to_table") or relation.get("to") or relation.get("target")
        child = relation.get("child_table") or relation.get("from_table") or relation.get("from") or relation.get("source")
        if parent and child:
            label = _relation_label(relation)
            parent_id = entity_identifier_by_physical.get(str(parent), _identifier(str(parent)))
            child_id = entity_identifier_by_physical.get(str(child), _identifier(str(child)))
            lines.append(f"    {parent_id} ||--o{{ {child_id} : {label}")
    return "\n".join(lines)


def build_erd_domain_summary_mermaid(structure: dict[str, Any]) -> str:
    entities = structure.get("entities") or structure.get("tables") or []
    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entity in entities:
        domain = str(entity.get("domain_group") or entity.get("table_type") or "ETC")
        by_domain[domain].append(entity)

    lines = ["flowchart TD"]
    for domain in sorted(by_domain):
        domain_id = _identifier(f"DOMAIN_{domain}")
        lines.append(f"    subgraph {domain_id}[{_summary_label(domain)}]")
        lines.append("        direction TB")
        for entity in by_domain[domain]:
            name = str(entity.get("entity_name") or entity.get("logical_name") or entity.get("name") or "")
            if not name:
                continue
            node_id = _identifier(f"{domain}_{name}")
            lines.append(f"        {node_id}[{_summary_label(name)}]")
        lines.append("    end")
    return "\n".join(lines)


def _core_columns(columns: list[dict[str, Any]], *, max_columns: int = 6) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for column in columns:
        if _is_core_column(column):
            selected.append(column)
    return selected[:max_columns]


def _is_core_column(column: dict[str, Any]) -> bool:
    constraints = [str(item).upper() for item in column.get("constraints") or []]
    name = str(column.get("physical_name") or column.get("column_name") or "").lower()
    logical = str(column.get("attribute_name") or column.get("logical_name") or column.get("description") or "").lower()
    return (
        bool(column.get("pk"))
        or bool(column.get("fk"))
        or "PK" in constraints
        or "FK" in constraints
        or name.endswith("_cd")
        or name.endswith("_yn")
        or "status" in name
        or "stts" in name
        or name.endswith("_nm")
        or "name" in name
        or name.endswith("_dt")
        or name.endswith("_at")
        or "date" in name
        or "일시" in logical
        or "날짜" in logical
        or "명" in logical
        or "상태" in logical
    )


def _relation_label(relation: dict[str, Any]) -> str:
    explicit = str(relation.get("relationship_label") or relation.get("label") or "").strip().lower()
    if explicit in {"has", "references", "belongs_to", "contains"}:
        return explicit
    relation_type = str(relation.get("relationship_type") or relation.get("type") or "").upper()
    if relation_type in {"1:N", "N:1"}:
        return "references"
    if relation_type in {"1:1"}:
        return "belongs_to"
    if relation_type in {"N:M", "M:N"}:
        return "has"
    return "references"


def _identifier(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z가-힣_]", "_", value).strip("_")
    if not normalized:
        return "item"
    if normalized[0].isdigit():
        return f"t_{normalized}"
    return normalized


def _entity_identifier(entity: dict[str, Any]) -> str:
    logical = str(entity.get("entity_name") or entity.get("logical_name") or entity.get("name") or "").strip()
    physical = str(entity.get("physical_name") or entity.get("table_name") or "").strip()
    return _identifier(logical or physical)


def _entity_identifier_map(entities: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        identifier = _entity_identifier(entity)
        for key in ("physical_name", "table_name", "name", "logical_name", "entity_name"):
            value = str(entity.get(key) or "").strip()
            if value:
                mapping[value] = identifier
    return mapping


def _data_type(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z_]", "_", value).strip("_").upper()
    return normalized or "VARCHAR"


def _label(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣_ -]", "", value).strip() or "relates"


def _summary_label(value: str) -> str:
    return (
        re.sub(r"[\[\]{}|\"']", "", value)
        .replace("(", "")
        .replace(")", "")
        .strip()
        or "ETC"
    )
