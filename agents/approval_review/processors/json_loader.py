import json
from typing import Any


def parse_content_text(value: str) -> dict[str, Any]:
    try:
        return {"content_type": "json", "data": json.loads(value)}
    except json.JSONDecodeError:
        return {"content_type": "raw_text", "data": value}
