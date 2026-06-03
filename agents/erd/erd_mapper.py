import hashlib
import json
import re
from typing import Any

from common.text_utils import extract_keywords, join_list


def build_table_structure_json(requirement_json: dict[str, Any], meeting_text: str) -> dict[str, Any]:
    keywords = extract_keywords(
        json.dumps(requirement_json, ensure_ascii=False) + "\n" + meeting_text,
        limit=40,
    )
    candidates = []
    seen_table_names = set()
    for keyword in keywords[:20]:
        if keyword.upper().startswith(("REQ", "SFR", "SEC")):
            continue
        table_name = to_table_name(keyword)
        if table_name in seen_table_names:
            continue
        seen_table_names.add(table_name)
        candidates.append(
            {
                "business_term": keyword,
                "table_name_candidate": table_name,
                "source": "requirement_or_meeting",
            }
        )
    return {"table_candidates": candidates}


def build_entity_candidate_json(table_structure_json: dict[str, Any]) -> dict[str, Any]:
    entities = []
    for idx, item in enumerate(table_structure_json.get("table_candidates", [])[:12], start=1):
        table_name = item.get("table_name_candidate") or f"tbl_entity_{idx:03d}"
        entities.append(
            {
                "entity_id": f"ENT-CAND-{idx:03d}",
                "entity_name": table_name.upper(),
                "entity_description": f"{item.get('business_term', '')} 관련 데이터",
            }
        )
    return {"entity_candidates": entities}


def build_requirement_context(requirement_json: dict[str, Any], meeting_text: str) -> dict[str, Any]:
    requirements = requirement_json.get("requirements", [])
    if not requirements:
        raise ValueError("요구사항 정의서에서 requirements를 찾지 못했습니다.")

    descriptions = []
    validations = []
    names = []
    ids = []
    for item in requirements:
        req_id = item.get("requirement_id", "")
        req_name = item.get("requirement_name", "")
        prefix = f"[{req_id}] {req_name}".strip()
        ids.append(req_id)
        names.append(req_name)
        descriptions.append(f"{prefix}\n{item.get('description', '')}".strip())
        validations.append(f"{prefix}\n{join_list(item.get('validation_criteria', []))}".strip())

    if meeting_text.strip():
        descriptions.append("[회의록 보강 내용]\n" + meeting_text[:6000])

    return {
        "requirement_id": "SYSTEM-ALL",
        "requirement_name": "요구사항 정의서 및 회의록 기반 통합 ERD",
        "requirement_type": "통합",
        "description": "\n\n".join(descriptions),
        "source": ["요구사항 정의서", "회의록"],
        "constraints": [],
        "priority": "통합",
        "validation_criteria": validations,
        "note": "DB 연동 ERD 생성 플로우에서 생성됨",
        "requirement_ids": ids,
        "requirement_names": names,
        "requirement_count": len(requirements),
    }


def normalize_final_erd_json(erd: dict[str, Any]) -> dict[str, Any]:
    if isinstance(erd.get("tables"), list):
        return erd

    tables = []
    for entity in erd.get("entities", []):
        table_name = str(entity.get("entity_name") or "").lower()
        columns = []
        for col in entity.get("columns", []):
            columns.append(
                {
                    "column_name": str(col.get("name") or "").lower(),
                    "data_type": normalize_data_type(col.get("type"), col.get("length")),
                    "comment": col.get("synonym") or col.get("constraint") or "",
                    "is_pk": col.get("pk") == "Y",
                    "is_fk": col.get("fk") == "Y",
                    "nullable": col.get("not_null") != "Y",
                    "default": col.get("default") or "",
                }
            )
        tables.append(
            {
                "table_name": table_name,
                "table_comment": entity.get("entity_description", ""),
                "columns": columns,
            }
        )

    relationships = []
    for rel in erd.get("relationships", []):
        relationships.append(
            {
                "from_table": str(rel.get("from_entity") or "").lower(),
                "from_column": "",
                "to_table": str(rel.get("to_entity") or "").lower(),
                "to_column": "",
                "type": rel.get("relationship", ""),
            }
        )

    return {
        "system_name": erd.get("system_name", ""),
        "erd_name": erd.get("erd_name", ""),
        "tables": tables,
        "relationships": relationships,
    }


def normalize_data_type(data_type: Any, length: Any = "") -> str:
    value = str(data_type or "VARCHAR").upper()
    if value == "NUMBER":
        value = "INT"
    if length and value in {"VARCHAR", "CHAR"}:
        return f"{value}({length})"
    return value


def to_table_name(keyword: str) -> str:
    value = re.sub(r"[^0-9A-Za-z가-힣]+", "_", keyword).strip("_")
    english = "_".join(re.findall(r"[A-Za-z0-9]+", value)).lower()
    if english:
        return "tbl_" + english
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
    return "tbl_" + digest
