# 최대 재시도 횟수와 재시도/재계획 가능 여부 정책을 정의합니다.

from typing import Any


DEFAULT_MAX_STEP_RETRY = 1

_TERMINAL_FAILURE_KEYWORDS = (
    "MISSING",
    "INVALID",
    "NOT_FOUND",
    "REQUIRED_INPUT",
)


def can_retry_step(
    agent_name: str,
    failure: dict[str, Any],
    retry_count: int,
    max_retry: int = DEFAULT_MAX_STEP_RETRY,
) -> bool:
    if agent_name == "validation_agent":
        return False
    if retry_count >= max_retry:
        return False
    if is_terminal_failure(str(failure.get("failure_type") or "")):
        return False
    return True


def is_terminal_failure(failure_type: str) -> bool:
    normalized = failure_type.upper()
    return any(keyword in normalized for keyword in _TERMINAL_FAILURE_KEYWORDS)


def can_replan(current_round: int, max_round: int) -> bool:
    return current_round < max_round
