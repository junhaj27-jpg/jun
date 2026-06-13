# 요구사항에서 도메인 그룹과 엔티티 후보를 추출합니다.

from typing import Any


DATA_NON_FUNCTIONAL_KEYWORDS = {"데이터", "개인정보", "이력", "권한", "보관"}
FUNCTION_TYPES = {"기능", "기능 요구사항", "functional", "function"}


def filter_data_requirements(items: list[Any]) -> list[dict[str, Any]]:
    selected = []
    for item in items:
        if not isinstance(item, dict):
            continue
        requirement_type = str(item.get("requirement_type") or "").lower()
        text = _text(item)
        if requirement_type in FUNCTION_TYPES or any(keyword in text for keyword in DATA_NON_FUNCTIONAL_KEYWORDS):
            selected.append(item)
    return selected


def build_domain_groups(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "domain_id": f"DOMAIN-{index + 1:03d}",
            "domain_name": _name(item),
            "source_requirement_ids": [str(item.get("req_id") or item.get("requirement_id") or f"REQ-{index + 1:03d}")],
            "description": _text(item),
        }
        for index, item in enumerate(items)
    ]


def build_entity_candidates(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    entities = []
    for group in groups:
        name = str(group["domain_name"]).replace(" 기능", "").replace(" 관리", "").strip() or "공통"
        if name in seen:
            continue
        seen.add(name)
        entities.append(
            {
                "entity_id": f"ENTITY-{len(entities) + 1:03d}",
                "logical_name": name,
                "description": group["description"],
                "source_requirement_ids": group["source_requirement_ids"],
            }
        )
    return entities


def _name(item: dict[str, Any]) -> str:
    return str(item.get("req_name") or item.get("requirement_name") or item.get("name") or "공통 데이터")


def _text(item: dict[str, Any]) -> str:
    return str(item.get("detail_text") or item.get("description") or item.get("content") or _name(item))
