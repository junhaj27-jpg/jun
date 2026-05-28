import json
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from agents.arch_nodes.analyze import analyze_requirements_node
from agents.arch_nodes.extract_infra import extract_infra_node
from agents.arch_nodes.generate_mermaid import generate_mermaid_node
from agents.arch_nodes.save_outputs import (
    generate_architecture_report_node,
    save_architecture_json_node,
)
from agents.arch_nodes.validate_mermaid import validate_mermaid_node
from workflows.architecture_state import ArchitectureWorkflowState


DEFAULT_ARCHITECTURE_REQUIREMENT_PATH = "./data/architecture/architecture_requirements.json"
DEFAULT_INFRA_SPEC_PATH = "./data/architecture/infra_spec.json"


def load_architecture_inputs_node(state: ArchitectureWorkflowState) -> ArchitectureWorkflowState:
    requirement_json_path = state.get("requirement_json_path") or DEFAULT_ARCHITECTURE_REQUIREMENT_PATH
    infra_spec_path = state.get("infra_spec_path") or DEFAULT_INFRA_SPEC_PATH

    with open(requirement_json_path, encoding="utf-8") as f:
        requirement_doc = json.load(f)

    if Path(infra_spec_path).exists():
        with open(infra_spec_path, encoding="utf-8") as f:
            user_infra_spec = json.load(f)
    else:
        user_infra_spec = {}

    return {
        "requirement_json_path": requirement_json_path,
        "infra_spec_path": infra_spec_path,
        "requirement_doc": requirement_doc,
        "user_infra_spec": user_infra_spec,
    }


def compile_architecture_graph():
    workflow = StateGraph(ArchitectureWorkflowState)

    workflow.add_node("load_architecture_inputs_node", load_architecture_inputs_node)
    workflow.add_node("analyze_requirements_node", analyze_requirements_node)
    workflow.add_node("extract_infra_node", extract_infra_node)
    workflow.add_node("generate_mermaid_node", generate_mermaid_node)
    workflow.add_node("validate_mermaid_node", validate_mermaid_node)
    workflow.add_node("save_architecture_json_node", save_architecture_json_node)
    workflow.add_node("generate_architecture_report_node", generate_architecture_report_node)

    workflow.add_edge(START, "load_architecture_inputs_node")
    workflow.add_edge("load_architecture_inputs_node", "analyze_requirements_node")
    workflow.add_edge("analyze_requirements_node", "extract_infra_node")
    workflow.add_edge("extract_infra_node", "generate_mermaid_node")
    workflow.add_edge("generate_mermaid_node", "validate_mermaid_node")
    workflow.add_edge("validate_mermaid_node", "save_architecture_json_node")
    workflow.add_edge("save_architecture_json_node", "generate_architecture_report_node")
    workflow.add_edge("generate_architecture_report_node", END)

    return workflow.compile()
