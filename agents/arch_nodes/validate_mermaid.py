from workflows.architecture_state import ArchitectureWorkflowState


def validate_mermaid_node(state: ArchitectureWorkflowState) -> ArchitectureWorkflowState:
    script = state.get("mermaid_script", "")
    retry_count = state.get("retry_count", 0)
    errors = []

    if "```mermaid" not in script:
        errors.append("Mermaid 코드 블록(```mermaid)을 찾을 수 없습니다.")

    if script.count("subgraph") != script.count("end"):
        errors.append(
            f"subgraph 개수({script.count('subgraph')})와 end 개수({script.count('end')})가 다릅니다."
        )

    if errors:
        return {
            "validation_result": {"status": "FAIL", "errors": errors},
            "retry_count": retry_count + 1,
            "status": "INVALID_MERMAID",
        }

    return {
        "validation_result": {"status": "PASS", "errors": []},
        "status": "VALID_MERMAID",
    }

