# 통합시험 시나리오별 시험 케이스를 생성하고 정제합니다.

from typing import Any


CASE_TYPES = ["NORMAL", "EXCEPTION", "AUTHORIZATION", "INPUT_VALIDATION", "STATE_CHANGE", "DATA_INTEGRITY"]


def generate_test_cases(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cases = []
    for scenario_index, scenario in enumerate(scenarios, start=1):
        for case_index, case_type in enumerate(CASE_TYPES, start=1):
            cases.append(
                {
                    "test_case_id": f"TC-{scenario_index:03d}-{case_index:02d}",
                    "scenario_id": scenario["scenario_id"],
                    "case_type": case_type,
                    "test_case_name": f"{scenario['scenario_name']} {case_type} 검증",
                    "source_requirement_ids": scenario.get("source_requirement_ids", []),
                }
            )
    return cases


def refine_test_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refined = []
    for index, case in enumerate(cases, start=1):
        refined.append(
            {
                **case,
                "test_case_id": str(case.get("test_case_id") or f"TC-{index:03d}"),
                "case_type": str(case.get("case_type") or "NORMAL").upper(),
                "test_case_name": str(case.get("test_case_name") or case.get("name") or f"시험 케이스 {index}"),
            }
        )
    return refined
