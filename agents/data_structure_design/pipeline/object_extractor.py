"""정규화된 요구사항에서 범용 도메인 객체 후보를 추출합니다."""

from typing import Any

from agents.data_structure_design.pipeline.rule_engine import GENERIC_ALIASES, GENERIC_OBJECT_RULES


def extract_domain_objects(requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    extracted: list[dict[str, Any]] = []
    for requirement in requirements:
        text = f"{requirement['requirement_name']}\n{requirement['detail']}"
        seen: set[tuple[str, str]] = set()
        for keyword, object_type, reason in _matching_rules(text):
            key = (_canonical_object_name(keyword), object_type)
            if key in seen:
                continue
            seen.add(key)
            extracted.append(
                {
                    "requirement_id": requirement["requirement_id"],
                    "requirement_type": requirement["requirement_type"],
                    "requirement_name": requirement["requirement_name"],
                    "name": key[0],
                    "object_type": object_type,
                    "reason": reason,
                }
            )
    return extracted


def _matching_rules(text: str) -> list[tuple[str, str, str]]:
    matches = [rule for rule in GENERIC_OBJECT_RULES if rule[0].lower() in text.lower()]
    if matches:
        return matches
    return [("업무", "MASTER", "요구사항에서 관리 대상 데이터가 도출됨")]


def _canonical_object_name(keyword: str) -> str:
    return GENERIC_ALIASES.get(keyword, keyword)
