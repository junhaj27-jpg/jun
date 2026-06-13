# 요구사항을 기반으로 통합시험 시나리오를 생성하고 정제합니다.

from copy import deepcopy
from typing import Any

from tools.llm.llm_client import LLMClient
from tools.llm.response_parser import parse_json_response
from tools.llm.send_api import send_parallel


FUNCTION_TYPES = {"기능", "기능 요구사항", "functional", "function"}


def filter_function_requirements(items: list[Any]) -> list[dict[str, Any]]:
    return [
        deepcopy(item)
        for item in items
        if isinstance(item, dict)
        and str(item.get("requirement_type") or item.get("type") or "").lower()
        in FUNCTION_TYPES
    ]


def generate_scenarios(
    requirements: list[dict[str, Any]],
    *,
    llm_client: LLMClient | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    scenarios, warnings = _parallel_or_fallback(
        requirements,
        llm_client,
        "요구사항별 업무 시험 시나리오를 JSON으로 생성하세요.",
        _fallback_scenario,
        "scenario",
    )
    return [_normalize_scenario(item, index) for index, item in enumerate(scenarios)], warnings


def refine_scenarios(
    scenarios: list[dict[str, Any]],
    *,
    llm_client: LLMClient | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    refined, warnings = _parallel_or_fallback(
        scenarios,
        llm_client,
        "시나리오 ID, 명칭, 누락 Step, 중복 Step, 요구사항 반영 여부를 검토하고 정제하세요.",
        _fallback_scenario,
        "scenario",
    )
    return [_normalize_scenario(item, index) for index, item in enumerate(refined)], warnings


def _parallel_or_fallback(items, llm_client, instruction, fallback, output_key):
    if llm_client is None:
        return [fallback(item, index) for index, item in enumerate(items)], []
    requests = [
        {"messages": [{"role": "system", "content": instruction}, {"role": "user", "content": str(item)}]}
        for item in items
    ]
    result = send_parallel(requests, client=llm_client)
    warnings = []
    output = []
    if result["success"]:
        for index, (item, response) in enumerate(zip(items, result["data"])):
            parsed = parse_json_response(response["data"]) if response and response["success"] else None
            value = parsed["data"] if parsed and parsed["success"] else None
            if isinstance(value, dict):
                value = value.get(output_key, value)
            output.append(value if isinstance(value, dict) else fallback(item, index))
            if not isinstance(value, dict):
                warnings.append({"code": "TS_SCENARIO_LLM_FALLBACK", "message": f"시나리오 {index + 1}을 기본값으로 대체했습니다."})
        return output, warnings
    return [fallback(item, index) for index, item in enumerate(items)], [{"code": "TS_SCENARIO_LLM_FAILED", "message": result["error"]["message"]}]


def _fallback_scenario(item: dict[str, Any], index: int) -> dict[str, Any]:
    return _normalize_scenario(item, index)


def _normalize_scenario(item: dict[str, Any], index: int) -> dict[str, Any]:
    requirement_id = str(item.get("req_id") or item.get("requirement_id") or item.get("source_requirement_id") or f"REQ-{index + 1:03d}")
    name = str(item.get("scenario_name") or item.get("req_name") or item.get("requirement_name") or item.get("name") or f"업무 시나리오 {index + 1}")
    return {
        **item,
        "scenario_id": f"SCN-{index + 1:03d}",
        "scenario_name": name,
        "source_requirement_ids": item.get("source_requirement_ids") or [requirement_id],
        "description": item.get("description") or item.get("detail_text") or f"{name} 기능을 검증합니다.",
    }
