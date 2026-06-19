from tools.result import ToolResult, error_result, success_result


def validate_mermaid(code: str, diagram_type: str | None = None) -> ToolResult:
    stripped = code.strip()
    if not stripped:
        return error_result("MERMAID_CODE_EMPTY", "Mermaid 코드가 비어 있습니다.")
    first_line = stripped.splitlines()[0].strip()
    allowed = {"erDiagram", "flowchart TD", "flowchart TB", "flowchart LR", "graph TD", "graph TB", "graph LR"}
    if diagram_type == "ERD" and first_line != "erDiagram":
        return error_result("MERMAID_ERD_HEADER_INVALID", "ERD Mermaid 코드는 erDiagram으로 시작해야 합니다.")
    if diagram_type == "ARCH" and not first_line.startswith(("flowchart", "graph")):
        return error_result("MERMAID_ARCH_HEADER_INVALID", "아키텍처 Mermaid 코드는 flowchart 또는 graph로 시작해야 합니다.")
    if not any(first_line.startswith(prefix) for prefix in allowed):
        return error_result("MERMAID_HEADER_INVALID", f"지원하지 않는 Mermaid 헤더입니다: {first_line}")
    if stripped.count("{") != stripped.count("}"):
        return error_result("MERMAID_BRACE_INVALID", "중괄호 개수가 일치하지 않습니다.")
    return success_result({"valid": True})
