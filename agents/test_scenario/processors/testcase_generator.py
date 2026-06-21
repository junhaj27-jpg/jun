# 통합시험 시나리오별 시험 케이스를 생성하고 정제합니다.

import re
from typing import Any

from agents.test_scenario.prompts import (
    SCENARIO_SUMMARY_PROMPT,
    TEST_CASE_GENERATION_PROMPT,
    compact_payload_for_ts,
    save_raw_output,
)
from tools.llm.llm_client import LLMClient
from tools.llm.response_parser import parse_json_response
from tools.llm.send_api import send_parallel


CASE_TYPES = ["NORMAL", "EXCEPTION", "AUTHORIZATION", "INPUT_VALIDATION", "STATE_CHANGE", "DATA_INTEGRITY"]

# 한글 케이스 타입 → 영문 정규화 매핑
_CASE_TYPE_MAP = {
    "정상": "NORMAL",
    "정상 케이스": "NORMAL",
    "경계값": "INPUT_VALIDATION",
    "경계값 케이스": "INPUT_VALIDATION",
    "경계값/입력값 검증 케이스": "INPUT_VALIDATION",
    "경계값/입력값 검증": "INPUT_VALIDATION",
    "입력값 검증": "INPUT_VALIDATION",
    "예외": "EXCEPTION",
    "예외 케이스": "EXCEPTION",
    "권한": "AUTHORIZATION",
    "권한 케이스": "AUTHORIZATION",
    "권한 검증": "AUTHORIZATION",
    "권한 검증 케이스": "AUTHORIZATION",
    "상태 변경": "STATE_CHANGE",
    "상태 변경 케이스": "STATE_CHANGE",
    "상태 변경 검증": "STATE_CHANGE",
    "상태 변경 검증 케이스": "STATE_CHANGE",
    "데이터 정합성": "DATA_INTEGRITY",
    "데이터 정합성 케이스": "DATA_INTEGRITY",
    "데이터 정합성 검증": "DATA_INTEGRITY",
    "데이터 정합성 검증 케이스": "DATA_INTEGRITY",
}

# 명사형으로 끝나지 않는 fallback/LLM 응답을 보정하기 위한 동사형 어미 → 명사형 치환 규칙
_VERBAL_ENDING_PATTERN = re.compile(r"(된다|한다|합니다|됩니다|된다\.|한다\.)$")


def _normalize_case_type(raw: str) -> str:
    """한글 또는 영문 케이스 타입을 표준 영문으로 정규화합니다."""
    stripped = raw.strip()
    return _CASE_TYPE_MAP.get(stripped) or _CASE_TYPE_MAP.get(stripped.upper()) or stripped.upper()


def generate_test_cases(
    scenarios: list[dict[str, Any]],
    *,
    llm_client: LLMClient | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if llm_client is None:
        return _fallback_cases_for_scenarios(scenarios), []

    result = send_parallel(
        [
            {
                "messages": [
                    {
                        "role": "system",
                        "content": TEST_CASE_GENERATION_PROMPT,
                    },
                    {"role": "user", "content": str(compact_payload_for_ts(scenario))},
                ]
            }
            for scenario in scenarios
        ],
        client=llm_client,
    )
    warnings: list[dict[str, Any]] = []
    if not result["success"]:
        return _fallback_cases_for_scenarios(scenarios), [
            {"code": "TS_TEST_CASE_LLM_FAILED", "message": result["error"]["message"]}
        ]

    cases: list[dict[str, Any]] = []
    for scenario_index, (scenario, response) in enumerate(zip(scenarios, result["data"]), start=1):
        generated = _parse_case_list(response)
        if not generated:
            raw_path = save_raw_output("test_case", scenario.get("scenario_id") or scenario_index, response["data"] if response else "")
            warnings.append(
                {
                    "code": "TS_TEST_CASE_LLM_FALLBACK",
                    "message": f"시나리오 {scenario_index}의 시험 케이스를 기본값으로 대체했습니다.",
                    "raw_output_path": raw_path,
                }
            )
            generated = _fallback_cases_for_scenario(scenario, scenario_index)
        cases.extend(
            _normalize_case(case, len(cases) + index + 1, scenario, scenario_index)
            for index, case in enumerate(generated)
        )
    return _ensure_case_type_coverage(cases, scenarios), warnings


def refine_test_cases(
    cases: list[dict[str, Any]],
    *,
    llm_client: LLMClient | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    fallback = [_normalize_case(case, index, None, 1) for index, case in enumerate(cases, start=1)]
    if llm_client is None:
        return fallback, []

    result = send_parallel(
        [
            {
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "시험 케이스별 품질을 검토하고 정제하세요. 정상 케이스, 예외 케이스, 권한 검증, "
                            "상태 변경 검증, 데이터 검증 존재 여부를 확인하고 JSON으로 test_case를 반환하세요."
                        ),
                    },
                    {"role": "user", "content": str(compact_payload_for_ts(case))},
                ]
            }
            for case in cases
        ],
        client=llm_client,
    )
    warnings: list[dict[str, Any]] = []
    if not result["success"]:
        return fallback, [{"code": "TS_TEST_CASE_REVIEW_LLM_FAILED", "message": result["error"]["message"]}]

    refined: list[dict[str, Any]] = []
    for index, (case, response) in enumerate(zip(cases, result["data"]), start=1):
        parsed = _parse_case(response)
        if parsed is None:
            raw_path = save_raw_output("test_case_refine", case.get("test_case_id") or index, response["data"] if response else "")
            warnings.append(
                {
                    "code": "TS_TEST_CASE_REVIEW_FALLBACK",
                    "message": f"시험 케이스 {index} 품질 검토 결과를 기본값으로 대체했습니다.",
                    "raw_output_path": raw_path,
                }
            )
            parsed = case
        refined.append(_normalize_case(parsed, index, None, 1))
    return refined, warnings


def generate_scenario_descriptions(
    cases: list[dict[str, Any]],
    steps_by_case: dict[str, list[dict[str, Any]]],
    *,
    llm_client: LLMClient | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """케이스별 확정된 시험 절차(step_detail)를 기반으로 명사형 시나리오 설명을 생성합니다.

    CBD 가이드 기준 '시나리오 설명'은 '시험 절차'(동사형 종결)와 달리,
    절차 내용을 하나의 문장으로 요약하고 명사형으로 종결해야 합니다.
    step_detail_json_list가 확정된 이후 호출하여, test_procedure 초안과
    최종 절차가 어긋나는 문제를 구조적으로 방지합니다.
    """

    if llm_client is None:
        return [
            {**case, "scenario_description_summary": _fallback_summary(case, steps_by_case)}
            for case in cases
        ], []

    requests = [
        {
            "messages": [
                {"role": "system", "content": SCENARIO_SUMMARY_PROMPT},
                {
                    "role": "user",
                    "content": str(
                        compact_payload_for_ts(_case_procedure_texts(case, steps_by_case))
                    ),
                },
            ]
        }
        for case in cases
    ]
    result = send_parallel(requests, client=llm_client)
    warnings: list[dict[str, Any]] = []
    if not result["success"]:
        return [
            {**case, "scenario_description_summary": _fallback_summary(case, steps_by_case)}
            for case in cases
        ], [{"code": "TS_SCENARIO_DESC_LLM_FAILED", "message": result["error"]["message"]}]

    updated: list[dict[str, Any]] = []
    for index, (case, response) in enumerate(zip(cases, result["data"]), start=1):
        summary = _parse_summary(response)
        if not summary:
            raw_path = save_raw_output(
                "scenario_description", case.get("test_case_id") or index, response["data"] if response else ""
            )
            warnings.append(
                {
                    "code": "TS_SCENARIO_DESC_FALLBACK",
                    "message": f"시험 케이스 {index}의 시나리오 설명을 기본값으로 대체했습니다.",
                    "raw_output_path": raw_path,
                }
            )
            summary = _fallback_summary(case, steps_by_case)
        else:
            summary = _ensure_nominal_ending(summary)
        updated.append({**case, "scenario_description_summary": summary})
    return updated, warnings


def _case_procedure_texts(case: dict[str, Any], steps_by_case: dict[str, list[dict[str, Any]]]) -> list[str]:
    case_steps = steps_by_case.get(case.get("test_case_id"), [])
    texts = [
        str(step.get("처리내용") or step.get("process") or "")
        for step in case_steps
        if isinstance(step, dict) and (step.get("처리내용") or step.get("process"))
    ]
    if texts:
        return texts
    procedure = case.get("test_procedure") or []
    return [
        str(item.get("처리내용") or item.get("process") or item)
        for item in procedure
        if item
    ]


def _parse_summary(response: Any) -> str | None:
    if not response or not response["success"]:
        return None
    parsed = parse_json_response(response["data"])
    if not parsed["success"]:
        return None
    value = parsed["data"]
    if isinstance(value, dict):
        summary = value.get("summary")
        return str(summary).strip() if summary else None
    return None


def _fallback_summary(case: dict[str, Any], steps_by_case: dict[str, list[dict[str, Any]]]) -> str:
    case_steps = steps_by_case.get(case.get("test_case_id"), [])
    if len(case_steps) == 1:
        text = str(case_steps[0].get("처리내용") or case_steps[0].get("process") or "")
        if text:
            return _ensure_nominal_ending(text)
    test_case_name = case.get("test_case_name") or "시험 케이스"
    return _ensure_nominal_ending(f"{test_case_name}")


def _ensure_nominal_ending(text: str) -> str:
    """동사형 종결(~한다/~된다 등)을 명사형으로 보정합니다."""
    cleaned = text.strip().rstrip(".")
    if _VERBAL_ENDING_PATTERN.search(cleaned):
        # 가장 단순한 보정: 동사형 어미를 제거하고 '검증'으로 종결
        cleaned = _VERBAL_ENDING_PATTERN.sub("", cleaned).strip()
        return f"{cleaned} 검증" if cleaned else "검증"
    return cleaned


def _fallback_cases_for_scenarios(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cases = []
    for scenario_index, scenario in enumerate(scenarios, start=1):
        cases.extend(_fallback_cases_for_scenario(scenario, scenario_index))
    return cases


def _fallback_cases_for_scenario(scenario: dict[str, Any], scenario_index: int) -> list[dict[str, Any]]:
    return [
        {
            "test_case_id": f"TC-{scenario_index:03d}-{case_index:02d}",
            "scenario_id": scenario["scenario_id"],
            "case_type": case_type,
            "test_case_name": f"{scenario['scenario_name']} {case_type} 검증",
            "source_requirement_ids": scenario.get("source_requirement_ids", []),
        }
        for case_index, case_type in enumerate(CASE_TYPES, start=1)
    ]


def _parse_case_list(response: Any) -> list[dict[str, Any]]:
    if not response or not response["success"]:
        return []
    parsed = parse_json_response(response["data"])
    if not parsed["success"]:
        return []
    value = parsed["data"]
    if isinstance(value, dict):
        value = value.get("test_case_json_list") or value.get("test_cases") or value.get("cases")
    if isinstance(value, list):
        return [_sanitize_case(item) for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [_sanitize_case(value)]
    return []


def _parse_case(response: Any) -> dict[str, Any] | None:
    if not response or not response["success"]:
        return None
    parsed = parse_json_response(response["data"])
    if not parsed["success"]:
        return None
    value = parsed["data"]
    if isinstance(value, dict):
        value = value.get("test_case") or value.get("case") or value
    return _sanitize_case(value) if isinstance(value, dict) else None


def _normalize_case(
    case: dict[str, Any],
    index: int,
    scenario: dict[str, Any] | None,
    scenario_index: int,
) -> dict[str, Any]:
    scenario_id = str(case.get("scenario_id") or (scenario or {}).get("scenario_id") or f"SCN-{scenario_index:03d}")
    scenario_name = str((scenario or {}).get("scenario_name") or case.get("scenario_name") or "업무 시나리오")
    raw_type = str(case.get("case_type") or "NORMAL")
    case_type = _normalize_case_type(raw_type)
    raw_id = str(case.get("test_case_id") or f"TC-{index:03d}")
    return {
        **case,
        "test_case_id": f"SCN{scenario_index:03d}-{raw_id}",
        "scenario_id": scenario_id,
        "case_type": case_type,
        "test_case_name": str(case.get("test_case_name") or case.get("name") or f"{scenario_name} 시험 케이스 {index}"),
        "source_requirement_ids": case.get("source_requirement_ids") or (scenario or {}).get("source_requirement_ids", []),
        "test_result": None,
    }


def _sanitize_case(case: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(case)
    sanitized["test_result"] = None
    for key in ("input_data", "입력값"):
        if key in sanitized and not isinstance(sanitized[key], str):
            sanitized[key] = " ".join(str(item) for item in sanitized[key]) if isinstance(sanitized[key], list) else str(sanitized[key])
    procedure = sanitized.get("test_procedure")
    if procedure is not None and not isinstance(procedure, list):
        sanitized["test_procedure"] = [str(procedure)]
    return sanitized


def _ensure_case_type_coverage(
    cases: list[dict[str, Any]],
    scenarios: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_scenario = {}
    for case in cases:
        by_scenario.setdefault(case["scenario_id"], []).append(case)

    covered: list[dict[str, Any]] = []
    for scenario_index, scenario in enumerate(scenarios, start=1):
        scenario_cases = list(by_scenario.get(scenario["scenario_id"], []))
        existing_types = {case["case_type"] for case in scenario_cases}
        scenario_cases.extend(
            case
            for case in _fallback_cases_for_scenario(scenario, scenario_index)
            if case["case_type"] not in existing_types
        )
        covered.extend(scenario_cases)
    return covered
