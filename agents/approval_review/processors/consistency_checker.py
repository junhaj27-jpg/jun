from __future__ import annotations

import json
from typing import Any

from agents.approval_review.prompts import CONSISTENCY_SYSTEM_PROMPT
from tools.llm.llm_client import LLMClient
from tools.llm.response_parser import parse_json_response


def check_consistency(
    reference: Any,
    target: Any,
    llm_client: LLMClient | None = None,
) -> dict[str, Any]:
    reference_items = extract_requirement_items(reference)
    target_items = extract_requirement_items(target)
    reference_ids = set(reference_items)
    target_ids = set(target_items)
    missing = sorted(reference_ids - target_ids)
    added = sorted(target_ids - reference_ids)
    matched = sorted(reference_ids & target_ids)

    messages = [
        {
            "type": "missing",
            "requirement_id": requirement_id,
            "text": f"{requirement_id} 요구사항이 승인 요청 산출물에 반영되지 않은 것으로 보입니다.",
        }
        for requirement_id in missing
    ]
    messages.extend(
        {
            "type": "added",
            "requirement_id": requirement_id,
            "text": f"{requirement_id} 항목은 최신 fix 요구사항 정의서에는 없지만 승인 요청 산출물에 포함되어 있습니다.",
        }
        for requirement_id in added
    )

    conflicts = _semantic_conflicts(
        [
            {
                "requirement_id": requirement_id,
                "requirement_content": reference_items[requirement_id],
                "artifact_content": target_items[requirement_id],
            }
            for requirement_id in matched
        ],
        llm_client,
    )
    messages.extend(conflicts)
    return {
        "status": "issues_found" if messages else "ok",
        "summary": {
            "matched_count": len(matched),
            "missing_count": len(missing),
            "added_count": len(added),
            "conflict_count": len(conflicts),
        },
        "messages": messages,
    }


def extract_requirement_items(value: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            requirement_id = node.get("requirement_id")
            if requirement_id not in (None, ""):
                result[str(requirement_id)] = node
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    return result


def _semantic_conflicts(
    pairs: list[dict[str, Any]], llm_client: LLMClient | None
) -> list[dict[str, Any]]:
    if not pairs:
        return []
    pairs = pairs[:10]
    client = llm_client or LLMClient(timeout=30)
    response = client.chat(
        [
            {"role": "system", "content": CONSISTENCY_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps({"matched_pairs": pairs}, ensure_ascii=False, default=str),
            },
        ],
        temperature=0,
        max_tokens=1200,
        extra_body={
            "think": False,
            "response_format": {"type": "json_object"},
        },
    )
    if not response["success"]:
        return []
    parsed = parse_json_response(response["data"])
    if not parsed["success"] or not isinstance(parsed["data"], dict):
        return []
    allowed_ids = {pair["requirement_id"] for pair in pairs}
    messages: list[dict[str, Any]] = []
    for item in parsed["data"].get("checks", []):
        if not isinstance(item, dict) or item.get("conflict") is not True:
            continue
        requirement_id = str(item.get("requirement_id") or "")
        if requirement_id not in allowed_ids:
            continue
        reason = str(item.get("reason") or "요구사항과 산출물 내용이 의미적으로 상충합니다.")
        messages.append(
            {
                "type": "conflict",
                "requirement_id": requirement_id,
                "text": f"{requirement_id} 항목의 의미적 상충이 확인되었습니다: {reason}",
            }
        )
    return messages
