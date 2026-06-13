import re
from typing import Any

from tools.llm.llm_client import LLMClient
from tools.llm.response_parser import parse_json_response


def rule_repair(code: str) -> str:
    repaired = code.replace('"', "").replace("'", "")
    repaired = re.sub(r"[()]", "", repaired)
    repaired = re.sub(r"(?m)^(\s*)([^\s\[\]{}|:-]+)\s+([^\[\]{}|:-]+)\s*-->", r"\1\2 -->", repaired)
    repaired = re.sub(r"(?m)^(\s*)([A-Za-z0-9_-]+)\s*\[([^\]]+)\]", lambda match: f'{match.group(1)}{_node_id(match.group(2))}[{match.group(3)}]', repaired)
    return repaired


def llm_repair(code: str, error_message: str, llm_client: LLMClient | None) -> str | None:
    if llm_client is None:
        return None
    result = llm_client.chat(
        [
            {"role": "system", "content": "오류가 있는 Mermaid 코드를 수정하고 mermaid_code JSON 필드로 반환하세요."},
            {"role": "user", "content": f"오류: {error_message}\n\n코드:\n{code}"},
        ]
    )
    if not result["success"]:
        return None
    parsed = parse_json_response(result["data"])
    if not parsed["success"]:
        return None
    value: Any = parsed["data"]
    if isinstance(value, dict):
        value = value.get("mermaid_code")
    return str(value).strip() if value else None


def _node_id(label: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]", "_", label).strip("_")
    return normalized or "NODE"
