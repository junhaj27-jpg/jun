from tools.result import ToolResult, error_result, success_result


def validate_mermaid(code: str, diagram_type: str | None = None) -> ToolResult:
    stripped = (code or "").strip()
    if not stripped:
        return error_result("MERMAID_CODE_EMPTY", "Mermaid 코드가 비어 있습니다.")

    first_diagram_line = _first_diagram_line(stripped)
    if not first_diagram_line:
        return error_result("MERMAID_HEADER_INVALID", "Mermaid 다이어그램 시작 라인을 찾을 수 없습니다.")

    if diagram_type == "ERD":
        if first_diagram_line != "erDiagram":
            return error_result(
                "MERMAID_ERD_HEADER_INVALID",
                "ERD Mermaid 코드는 erDiagram으로 시작해야 합니다.",
            )
    elif diagram_type == "ARCH":
        if not first_diagram_line.startswith(("flowchart", "graph")):
            return error_result(
                "MERMAID_ARCH_HEADER_INVALID",
                "아키텍처 Mermaid 코드는 flowchart 또는 graph로 시작해야 합니다.",
            )
    else:
        allowed_prefixes = ("erDiagram", "flowchart", "graph")
        if not first_diagram_line.startswith(allowed_prefixes):
            return error_result(
                "MERMAID_HEADER_INVALID",
                f"지원하지 않는 Mermaid 헤더입니다: {first_diagram_line}",
            )

    # Mermaid init directive의 JSON 중괄호는 문법 오류가 아니므로 단순 중괄호 개수 검사는 하지 않는다.
    return success_result({"valid": True})


def _first_diagram_line(code: str) -> str:
    """Mermaid init directive/comment를 건너뛰고 실제 다이어그램 시작 라인을 반환합니다."""

    for line in code.splitlines():
        current = line.strip()
        if not current:
            continue
        if current.startswith("%%"):
            continue
        return current
    return ""
