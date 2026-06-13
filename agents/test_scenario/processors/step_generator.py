# 시험 절차, 입력값 및 예상 결과를 생성하고 정제합니다.

from typing import Any


def generate_steps(
    test_cases: list[dict[str, Any]],
    interfaces: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    steps = []
    for index, case in enumerate(test_cases, start=1):
        interface = _find_interface(case, interfaces)
        screen_id = str(interface.get("screen_id") or interface.get("interface_id") or "N/A") if interface else "N/A"
        screen_description = str(interface.get("description") or "") if interface else ""
        steps.append(
            {
                "step_id": f"STEP-{index:04d}",
                "test_case_id": case["test_case_id"],
                "step_no": 1,
                "처리내용": f"{case['test_case_name']}을 수행한다.",
                "시험항목": case["test_case_name"],
                "사전조건": "시험 대상 시스템에 접근할 수 있어야 한다.",
                "입력값": _input_for_type(case["case_type"]),
                "예상결과": f"{case['case_type']} 처리 결과가 요구사항과 일치해야 한다. {screen_description}".strip(),
                "화면ID": screen_id,
                "screen_id": screen_id,
            }
        )
    return steps


def refine_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refined = []
    for index, step in enumerate(steps, start=1):
        refined.append(
            {
                **step,
                "step_id": str(step.get("step_id") or f"STEP-{index:04d}"),
                "step_no": step.get("step_no") or index,
                "처리내용": step.get("처리내용") or step.get("process") or step.get("action") or "시험 절차를 수행한다.",
                "시험항목": step.get("시험항목") or step.get("test_item") or "기능 검증",
                "사전조건": step.get("사전조건") or step.get("precondition") or "사전조건을 확인한다.",
                "입력값": step.get("입력값") or step.get("input") or step.get("input_value") or "유효한 시험 데이터",
                "예상결과": step.get("예상결과") or step.get("expected_result") or "기대 결과와 일치한다.",
                "화면ID": step.get("화면ID") or step.get("screen_id") or "N/A",
                "screen_id": step.get("screen_id") or step.get("화면ID") or "N/A",
            }
        )
    return refined


def _find_interface(case: dict[str, Any], interfaces: list[dict[str, Any]]) -> dict[str, Any] | None:
    requirement_ids = set(map(str, case.get("source_requirement_ids", [])))
    for interface in interfaces:
        matched = interface.get("matched_requirement_ids") or interface.get("requirement_ids") or []
        if requirement_ids.intersection(map(str, matched)):
            return interface
    return interfaces[0] if interfaces else None


def _input_for_type(case_type: str) -> str:
    return "유효하지 않은 시험 데이터" if case_type in {"EXCEPTION", "INPUT_VALIDATION"} else "유효한 시험 데이터"
