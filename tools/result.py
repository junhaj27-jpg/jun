from typing import Any, TypedDict


class ToolResult(TypedDict):
    success: bool
    data: Any
    error: dict[str, Any] | None


def success_result(data: Any) -> ToolResult:
    return {"success": True, "data": data, "error": None}


def error_result(code: str, message: str, details: Any = None) -> ToolResult:
    return {
        "success": False,
        "data": None,
        "error": {"code": code, "message": message, "details": details},
    }
