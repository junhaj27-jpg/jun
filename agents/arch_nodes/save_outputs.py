import json
from pathlib import Path

from generators.architecture_report_generator import generate_architecture_report
from workflows.architecture_state import ArchitectureWorkflowState


def save_architecture_json_node(state: ArchitectureWorkflowState) -> ArchitectureWorkflowState:
    output_json_path = state.get("output_json_path") or "./json_temp/architecture_agent_output.json"
    payload = {
        "requirement_doc": state.get("requirement_doc", {}),
        "user_infra_spec": state.get("user_infra_spec", {}),
        "analyzed_reqs": state.get("analyzed_reqs", []),
        "extracted_infra": state.get("extracted_infra", {}),
        "report_specs": state.get("report_specs", ""),
        "mermaid_script": state.get("mermaid_script", ""),
        "validation_result": state.get("validation_result", {}),
    }
    Path(output_json_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_json_path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"output_json_path": output_json_path}


def generate_architecture_report_node(state: ArchitectureWorkflowState) -> ArchitectureWorkflowState:
    result = generate_architecture_report(
        report_specs=state.get("report_specs", ""),
        mermaid_script=state.get("mermaid_script", ""),
        output_md_path=state.get("output_md_path") or "./output/architecture_report.md",
        output_docx_path=state.get("output_docx_path") or "./output/architecture_report.docx",
        output_image_path=state.get("output_image_path") or "./output/architecture_diagram.png",
        render_image=state.get("render_image", True),
    )
    return {
        "output_md_path": result.get("md_path"),
        "output_docx_path": result.get("docx_path"),
        "output_image_path": result.get("image_path"),
        "status": "VALID",
    }

