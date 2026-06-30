"""정규화된 요구사항에서 범용 도메인 객체 후보를 추출합니다."""

from typing import Any
import re

from agents.data_structure_design.pipeline.rule_engine import GENERIC_ALIASES, GENERIC_OBJECT_RULES


def extract_domain_objects(requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    extracted: list[dict[str, Any]] = []
    for requirement in requirements:
        text = f"{requirement['requirement_name']}\n{requirement['detail']}"
        seen: set[tuple[str, str]] = set()
        matches = _matching_rules(text)
        if not matches:
            fallback_name = _fallback_object_name(requirement)
            matches = [(fallback_name, "MASTER", "요구사항 명칭에서 관리 대상을 추출함")]
        for keyword, object_type, reason in matches:
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
    return [rule for rule in GENERIC_OBJECT_RULES if rule[0].lower() in text.lower()]


def _fallback_object_name(requirement: dict[str, Any]) -> str:
    text = str(requirement.get("requirement_name") or "").strip()
    text = re.sub(r"(기능|관리|처리|제공|등록|조회|수정|삭제|요구사항)$", "", text).strip()
    text = re.sub(r"[^0-9A-Za-z가-힣 ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:40] or str(requirement.get("requirement_id") or "미분류")


def _canonical_object_name(keyword: str) -> str:
    return GENERIC_ALIASES.get(keyword, keyword)
