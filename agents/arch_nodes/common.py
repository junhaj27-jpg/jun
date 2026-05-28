import json
import re
from typing import Any


def extract_json(value: str) -> Any:
    text = str(value or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```json\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))

    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))

    raise ValueError("LLM 응답에서 JSON을 찾지 못했습니다.")


def strip_mermaid_block(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^`{1,3}\s*mermaid\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"`{1,3}\s*$", "", text)
    text = text.replace("```mermaid", "").replace("```", "")
    return text.strip()


def normalize_mermaid_syntax(value: str) -> str:
    """Fix common LLM Mermaid mistakes that break rendering."""
    script = strip_mermaid_block(value)

    def safe_id(raw: str) -> str:
        return re.sub(r"[^A-Za-z0-9_]", "_", raw.strip()).strip("_").upper() or "NODE"

    def replace_declaration(match: re.Match) -> str:
        return f"{safe_id(match.group('id'))}{match.group('shape')}"

    declaration_pattern = re.compile(
        r"(?P<id>[A-Za-z][A-Za-z0-9_-]*(?:[\s-]+[A-Za-z][A-Za-z0-9_-]*)+)\s*(?P<shape>[\[\(\{])"
    )

    normalized_lines = []
    for line in script.splitlines():
        fixed = declaration_pattern.sub(replace_declaration, line)

        fixed = re.sub(
            r"^(\s*)([A-Za-z][A-Za-z0-9_-]*(?:[\s-]+[A-Za-z][A-Za-z0-9_-]*)+)(\s*[-=.ox|{}]+>\s*)",
            lambda m: f"{m.group(1)}{safe_id(m.group(2))}{m.group(3)}",
            fixed,
        )
        fixed = re.sub(
            r"([-=.ox|{}]+>\s*)([A-Za-z][A-Za-z0-9_-]*(?:[\s-]+[A-Za-z][A-Za-z0-9_-]*)+)(?=\s*(?:[\[\(\{]|$))",
            lambda m: f"{m.group(1)}{safe_id(m.group(2))}",
            fixed,
        )
        normalized_lines.append(fixed)

    return "\n".join(normalized_lines).strip()


def wrap_mermaid_block(value: str) -> str:
    return f"```mermaid\n{normalize_mermaid_syntax(value)}\n```"
