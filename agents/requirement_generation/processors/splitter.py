from copy import deepcopy
from typing import Any


def filter_function_requirements(items: list[Any]) -> list[dict[str, Any]]:
    return [
        deepcopy(item)
        for item in items
        if isinstance(item, dict)
        and _is_functional_type(item.get("requirement_type") or item.get("type"))
    ]


def _is_functional_type(value: Any) -> bool:
    requirement_type = str(value or "").strip().lower()
    return (
        requirement_type.startswith("기능")
        or requirement_type.startswith("functional")
        or requirement_type == "function"
    )
