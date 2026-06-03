from datetime import datetime
from typing import Any


def final_erd_to_template_erd(final_erd_json: dict[str, Any]) -> dict[str, Any]:
    if final_erd_json.get("entities"):
        return final_erd_json

    entities = []
    for idx, table in enumerate(final_erd_json.get("tables", []), start=1):
        columns = []
        for col in table.get("columns", []):
            columns.append(
                {
                    "name": str(col.get("column_name") or "").upper(),
                    "synonym": col.get("comment", ""),
                    "type": col.get("data_type", "VARCHAR"),
                    "length": "",
                    "not_null": "Y" if not col.get("nullable", True) else "",
                    "pk": "Y" if col.get("is_pk") else "",
                    "fk": "Y" if col.get("is_fk") else "",
                    "inx": "Y" if col.get("is_pk") or col.get("is_fk") else "",
                    "default": col.get("default", ""),
                    "constraint": col.get("comment", ""),
                }
            )
        entities.append(
            {
                "entity_id": f"ENT-{idx:03d}",
                "entity_name": str(table.get("table_name") or f"tbl_entity_{idx:03d}").upper(),
                "entity_description": table.get("table_comment", ""),
                "columns": columns,
            }
        )

    relationships = []
    for rel in final_erd_json.get("relationships", []):
        relationships.append(
            {
                "from_entity": str(rel.get("from_table") or "").upper(),
                "to_entity": str(rel.get("to_table") or "").upper(),
                "relationship": rel.get("type") or "1:N",
                "description": f"{rel.get('from_column', '')} -> {rel.get('to_column', '')}".strip(" ->"),
            }
        )

    return {
        "system_name": final_erd_json.get("system_name", "프로젝트"),
        "stage_name": "설계",
        "created_date": datetime.now().strftime("%Y-%m-%d"),
        "version": "v1.0",
        "erd_id": "ERD-SYSTEM-ALL",
        "erd_name": final_erd_json.get("erd_name", "통합 ERD"),
        "requirement_id": "SYSTEM-ALL",
        "requirement_name": "요구사항 정의서 및 회의록 기반 통합 ERD",
        "entities": entities,
        "relationships": relationships,
    }
