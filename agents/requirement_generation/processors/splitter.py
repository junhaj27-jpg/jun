# 기능 요구사항을 업무 단위로 분해합니다.

import json
from copy import deepcopy
from typing import Any

from tools.llm.llm_client import LLMClient
from tools.llm.response_parser import parse_json_response


FUNCTION_TYPES = {"기능", "기능 요구사항", "functional", "function"}


def filter_function_requirements(items: list[Any]) -> list[dict[str, Any]]:
    return [
        deepcopy(item)
        for item in items
        if isinstance(item, dict)
        and str(item.get("requirement_type") or item.get("type") or "").strip().lower()
        in FUNCTION_TYPES
    ]


def build_integrated_text(items: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"[{_source_id(item)}] {_name(item)}\n{_description(item)}" for item in items
    )


def split_function_requirements(
    items: list[dict[str, Any]],
    integrated_text: str,
    *,
    llm_client: LLMClient | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    if llm_client is not None:
        result = llm_client.chat(
            [
                {
                    "role": "system",
                    "content": "기능 요구사항을 독립적으로 검증 가능한 업무 단위 JSON 목록으로 분해하세요.",
                },
                {"role": "user", "content": integrated_text},
            ]
        )
        if result["success"]:
            parsed = parse_json_response(result["data"])
            if parsed["success"]:
                value = parsed["data"]
                if isinstance(value, dict):
                    value = value.get("split_function_requirement_list", value.get("requirements"))
                if isinstance(value, list) and value:
                    return [_normalize_split(item, index) for index, item in enumerate(value)], warnings
        warnings.append({"code": "REQUIREMENT_SPLIT_LLM_FALLBACK", "message": "SLLM 분해에 실패하여 원본 기능 요구사항 단위를 사용합니다."})
    return [_normalize_split(item, index) for index, item in enumerate(items)], warnings


def _normalize_split(item: Any, index: int) -> dict[str, Any]:
    source = item if isinstance(item, dict) else {"description": str(item)}
    source_ids = source.get("source_req_ids") or source.get("source") or [_source_id(source)]
    if not isinstance(source_ids, list):
        source_ids = [source_ids]
    return {
        **source,
        "requirement_id": source.get("requirement_id") or source.get("req_id") or f"FUR-{index + 1:03d}",
        "requirement_name": source.get("requirement_name") or source.get("req_name") or source.get("name") or f"기능 요구사항 {index + 1}",
        "description": _description(source),
        "source": [str(value) for value in source_ids if value],
    }


def _source_id(item: dict[str, Any]) -> str:
    return str(item.get("req_id") or item.get("requirement_id") or item.get("id") or "UNKNOWN")


def _name(item: dict[str, Any]) -> str:
    return str(item.get("req_name") or item.get("requirement_name") or item.get("name") or "")


def _description(item: dict[str, Any]) -> str:
    return str(item.get("detail_text") or item.get("description") or item.get("content") or json.dumps(item, ensure_ascii=False))
