from __future__ import annotations

from typing import Final


GENERIC_REQUIREMENT_GOLD_ERROR_CODE: Final[str] = "REQUIREMENT_GOLD_GENERATION_FAILED"


class RequirementGoldError(RuntimeError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def get_requirement_gold_error_code(exc: BaseException) -> str:
    explicit_code = getattr(exc, "error_code", None)
    if explicit_code:
        return str(explicit_code)

    message = str(exc).lower()
    error_type = type(exc).__name__.lower()

    if "hf_token" in message:
        return "REQUIREMENT_GOLD_HF_TOKEN_MISSING"
    if "cuda gpu" in message:
        return "REQUIREMENT_GOLD_CUDA_UNAVAILABLE"
    if "context limit" in message:
        return "REQUIREMENT_GOLD_CONTEXT_LIMIT_EXCEEDED"
    if "json_repair" in message:
        return "REQUIREMENT_GOLD_OUTPUT_INVALID"
    if "free=" in message and "gpu" in message:
        return "REQUIREMENT_GOLD_GPU_MEMORY_LOW"
    if "from_pretrained" in message or "load_adapter" in message:
        return "REQUIREMENT_GOLD_MODEL_LOAD_FAILED"
    if "repository not found" in message or "401 client error" in message or "404 client error" in message:
        return "REQUIREMENT_GOLD_MODEL_LOAD_FAILED"
    if error_type == "validationerror":
        return "REQUIREMENT_GOLD_OUTPUT_INVALID"
    return GENERIC_REQUIREMENT_GOLD_ERROR_CODE


def build_retry_error_prompt(
    exc: BaseException,
    traceback_text: str | None,
    *,
    limit: int = 1500,
) -> str:
    lines = [
        f"error_code: {get_requirement_gold_error_code(exc)}",
        f"error_type: {type(exc).__name__}",
        f"message: {exc}",
    ]
    if traceback_text:
        trimmed_traceback = traceback_text.strip()
        if trimmed_traceback:
            lines.append("traceback_tail:")
            lines.extend(trimmed_traceback.splitlines()[-8:])
    rendered = "\n".join(lines).strip()
    if len(rendered) <= limit:
        return rendered
    return rendered[: max(limit - 3, 0)] + "..."
