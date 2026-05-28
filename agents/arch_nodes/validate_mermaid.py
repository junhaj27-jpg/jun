from workflows.architecture_state import ArchitectureWorkflowState
from agents.arch_nodes.common import normalize_mermaid_syntax, wrap_mermaid_block


def validate_mermaid_node(state: ArchitectureWorkflowState) -> ArchitectureWorkflowState:
    script = wrap_mermaid_block(state.get("mermaid_script", ""))
    clean_script = normalize_mermaid_syntax(script)
    errors = []

    if "```mermaid" not in script:
        errors.append("Mermaid 코드 블록(```mermaid)을 찾을 수 없습니다.")

    if clean_script.count("subgraph") != clean_script.count("end"):
        errors.append(
            f"subgraph 개수({clean_script.count('subgraph')})와 end 개수({clean_script.count('end')})가 다릅니다."
        )

    if errors:
        return {
            "validation_result": {"status": "FAIL", "errors": errors},
            "mermaid_script": script,
            "status": "INVALID_MERMAID",
        }

    return {
        "validation_result": {"status": "PASS", "errors": []},
        "mermaid_script": script,
        "status": "VALID_MERMAID",
    }
