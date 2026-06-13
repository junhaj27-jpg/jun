# 각 실행 단계에서 생성된 Agent 결과를 평가합니다.

from typing import Any

from supervisor.evaluate.result_checker import check_agent_result


def evaluate_step(
    agent_name: str,
    output: dict[str, Any] | None,
    required_output_keys: list[str],
) -> dict[str, Any]:
    result = check_agent_result(agent_name, output, required_output_keys)
    if not result["success"] or agent_name != "validation_agent":
        return result

    validation_result = output.get("validation_result", {}) if output else {}
    validation_status = validation_result.get("validation_status")
    if validation_status == "PASS":
        return {**result, "action": "REDUCE"}
    if validation_status == "PARTIAL_PASS" and not _has_high_severity_failure(
        validation_result.get("checks", [])
    ):
        return {**result, "action": "REDUCE"}

    failure_type = _first_failure_type(validation_result.get("checks", []))
    return {
        "success": False,
        "failure_type": failure_type or "VALIDATION_FAILED",
        "message": f"validation_status={validation_status}",
        "action": "REPLAN",
    }


def _has_high_severity_failure(checks: list[dict[str, Any]]) -> bool:
    return any(
        check.get("status") == "FAIL" and check.get("severity") == "HIGH"
        for check in checks
    )


def _first_failure_type(checks: list[dict[str, Any]]) -> str | None:
    for check in checks:
        if check.get("status") == "FAIL" and check.get("failure_type"):
            return str(check["failure_type"])
    return None
