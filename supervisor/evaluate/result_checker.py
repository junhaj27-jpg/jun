# Agent 출력의 존재 여부, 빈값 및 상태를 검증합니다.

from typing import Any


def is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def check_agent_result(
    agent_name: str,
    output: dict[str, Any] | None,
    required_output_keys: list[str],
) -> dict[str, Any]:
    if output is None:
        return _failure(f"{agent_name.upper()}_OUTPUT_MISSING", "Agent output이 없습니다.")
    allowed_statuses = (
        {"SUCCESS", "PASS", "FAIL", "PARTIAL_PASS"}
        if agent_name == "validation_agent"
        else {"SUCCESS"}
    )
    if output.get("status") not in allowed_statuses:
        return _failure(
            str(output.get("failure_type") or f"{agent_name.upper()}_STATUS_FAILED"),
            "Agent status가 SUCCESS가 아닙니다.",
        )
    if output.get("errors"):
        return _failure(
            str(output.get("failure_type") or f"{agent_name.upper()}_ERRORS_PRESENT"),
            "Agent output에 errors가 존재합니다.",
        )

    missing = [key for key in required_output_keys if key not in output or is_empty(output[key])]
    if missing:
        return _failure(
            str(output.get("failure_type") or f"{agent_name.upper()}_REQUIRED_OUTPUT_MISSING"),
            f"필수 output이 없거나 비어 있습니다: {missing}",
        )
    return {"success": True, "failure_type": None, "message": None}


def _failure(failure_type: str, message: str) -> dict[str, Any]:
    return {"success": False, "failure_type": failure_type, "message": message}
