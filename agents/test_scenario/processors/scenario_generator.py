# 요구사항을 기반으로 통합시험 시나리오를 생성하고 정제합니다.

from copy import deepcopy
from typing import Any

from agents.test_scenario.prompts import (
    SCENARIO_GENERATION_PROMPT,
    compact_payload_for_ts,
    save_raw_output,
)
from tools.llm.llm_client import LLMClient
from tools.llm.response_parser import parse_json_response
from tools.llm.send_api import send_parallel


def filter_function_requirements(items: list[Any]) -> list[dict[str, Any]]:
    return [
        deepcopy(item)
        for item in items
        if isinstance(item, dict)
        and _is_functional_type(item.get("requirement_type") or item.get("type"))
    ]


def _is_functional_type(value: Any) -> bool:
    requirement_type = str(value or "").strip().lower()
    return requirement_type.startswith("기능") or requirement_type.startswith("functional") or requirement_type == "function"


def generate_scenarios(
    requirements: list[dict[str, Any]],
    *,
    llm_client: LLMClient | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    scenarios, warnings = _parallel_or_fallback(
        requirements,
        llm_client,
        SCENARIO_GENERATION_PROMPT,
        _fallback_scenario,
        "scenario",
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
        "scenario_refine",
    )
    return [_normalize_scenario(item, index) for index, item in enumerate(refined)], warnings


def apply_scenario_rules(
    artifacts: list[dict[str, Any]],
    *,
    llm_client: LLMClient | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """수정 모드 산출물 JSON에 시나리오 작성 규칙을 먼저 적용합니다."""

    fallback = [deepcopy(item) for item in artifacts]
    if llm_client is None:
        return fallback, []

    result = llm_client.chat(
        [
            {
                "role": "system",
                "content": (
                    "통합시험 시나리오 수정 산출물에 작성 규칙을 적용하세요. "
                    "Scenario ID, Test Case ID, Step 번호, 명칭, 작성 형식, 화면ID 규칙을 정리하고 "
                    "JSON으로 integrated_artifact_json_list 또는 scenario_rule_applied_json_list를 반환하세요."
                ),
            },
            {"role": "user", "content": str({"integrated_artifact_json_list": artifacts})},
        ]
    )
    if not result["success"]:
        return fallback, [{"code": "TS_SCENARIO_RULE_LLM_FAILED", "message": result["error"]["message"]}]

    parsed = parse_json_response(result["data"])
    if not parsed["success"]:
        return fallback, [{"code": "TS_SCENARIO_RULE_PARSE_FAILED", "message": parsed["error"]["message"]}]

    value = parsed["data"]
    if isinstance(value, dict):
        value = (
            value.get("integrated_artifact_json_list")
            or value.get("scenario_rule_applied_json_list")
            or value.get("artifacts")
        )
    if isinstance(value, list):
        items = [item for item in value if isinstance(item, dict)]
        if items:
            return items, []
    return fallback, [{"code": "TS_SCENARIO_RULE_FALLBACK", "message": "시나리오 작성 규칙 적용 결과를 기본값으로 대체했습니다."}]


def _parallel_or_fallback(items, llm_client, instruction, fallback, output_key, stage):
    if llm_client is None:
        return [fallback(item, index) for index, item in enumerate(items)], []
    requests = [
        {"messages": [{"role": "system", "content": instruction}, {"role": "user", "content": str(compact_payload_for_ts(item))}]}
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
                raw_path = save_raw_output(stage, _requirement_id(item, index), response["data"] if response else "")
                warnings.append({
                    "code": "TS_SCENARIO_LLM_FALLBACK",
                    "message": f"시나리오 {index + 1}을 기본값으로 대체했습니다.",
                    "raw_output_path": raw_path,
                })
        return output, warnings
    return [fallback(item, index) for index, item in enumerate(items)], [{"code": "TS_SCENARIO_LLM_FAILED", "message": result["error"]["message"]}]


def _fallback_scenario(item: dict[str, Any], index: int) -> dict[str, Any]:
    return _normalize_scenario(item, index)


def _normalize_scenario(item: dict[str, Any], index: int) -> dict[str, Any]:
    requirement_id = _requirement_id(item, index)
    name = str(item.get("scenario_name") or item.get("req_name") or item.get("requirement_name") or item.get("name") or f"업무 시나리오 {index + 1}")
    return {
        **item,
        "scenario_id": f"SCN-{index + 1:03d}",
        "scenario_name": name,
        "source_requirement_ids": item.get("source_requirement_ids") or [requirement_id],
        "description": item.get("description") or item.get("scenario_description") or item.get("detail_text") or f"{name} 기능을 검증합니다.",
    }


def _requirement_id(item: dict[str, Any], index: int) -> str:
    return str(item.get("req_id") or item.get("requirement_id") or item.get("source_requirement_id") or f"REQ-{index + 1:03d}")
