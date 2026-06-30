import json
from typing import Any

from tools.llm.json_repair import repair_json_text
from tools.result import ToolResult, error_result, success_result


def parse_json_response(response: Any, *, repair: bool = True) -> ToolResult:
    """LLM 응답 문자열 또는 OpenAI 호환 응답에서 JSON 값을 추출합니다."""

    try:
        if isinstance(response, (dict, list)):
            if isinstance(response, dict) and "choices" in response:
                text = response["choices"][0]["message"]["content"]
            elif isinstance(response, dict) and "content" in response:
                text = response["content"]
            else:
                return success_result(response)
        else:
            text = str(response)
        return success_result(json.loads(text))
    except (KeyError, IndexError, TypeError) as exc:
        return error_result("LLM_RESPONSE_FORMAT_ERROR", str(exc))
    except json.JSONDecodeError as exc:
        if repair:
            repaired = repair_json_text(text)
            if repaired["success"]:
                return success_result(repaired["data"]["value"])
        return error_result("LLM_RESPONSE_JSON_ERROR", str(exc), {"text": text})
