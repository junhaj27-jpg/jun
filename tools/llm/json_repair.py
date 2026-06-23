import json
import re

from tools.result import ToolResult, error_result, success_result


def repair_json_text(text: str) -> ToolResult:
    """기본 보정만 수행합니다. 복합 JSON 복구 규칙은 추후 구현합니다."""

    # TODO: 중괄호 불일치 등 복합 손상 JSON 복구 규칙을 추가합니다.
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)
    if not cleaned.startswith(("{", "[")):
        object_start = cleaned.find("{")
        object_end = cleaned.rfind("}")
        array_start = cleaned.find("[")
        array_end = cleaned.rfind("]")
        if object_start >= 0 and object_end > object_start:
            cleaned = cleaned[object_start : object_end + 1]
        elif array_start >= 0 and array_end > array_start:
            cleaned = cleaned[array_start : array_end + 1]

    try:
        return success_result({"text": cleaned, "value": json.loads(cleaned)})
    except json.JSONDecodeError as exc:
        return error_result("JSON_REPAIR_FAILED", str(exc), {"text": cleaned})
