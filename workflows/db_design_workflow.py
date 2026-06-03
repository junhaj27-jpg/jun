import json
from pathlib import Path
from typing import Any, Dict, List

from langgraph.graph import END, START, StateGraph

from agents.db.database_design_agent import (
    OUTPUT_JSON_PATH,
    build_database_design,
    build_database_design_rag_context,
    enhance_database_design_with_rag,
    parse_erd_docx,
    resolve_erd_docx_path,
)
from agents.erd.erd_agent import REQ_JSON_PATH
from generators.db.docx_generator import (
    OUTPUT_PATH,
    generate_database_design_docx,
)
from workflows.db_design_state import DatabaseDesignWorkflowState
from workflows.erd_workflow import build_system_context


def _load_requirement(requirement_json_path: str) -> Dict[str, Any]:
    with open(requirement_json_path, "r", encoding="utf-8") as f:
        requirement_doc = json.load(f)

    system_context = build_system_context(requirement_doc)

    return {
        "requirement_doc": requirement_doc,
        "system_context": system_context,
    }


def _validate_database_design(design: Dict[str, Any]) -> List[str]:
    errors = []
    if not design.get("system_name"):
        errors.append("system_name 누락")
    if not design.get("databases"):
        errors.append("databases는 1개 이상이어야 합니다.")
    tables = design.get("tables", [])
    if not tables:
        errors.append("tables는 1개 이상이어야 합니다.")

    for table_idx, table in enumerate(tables, start=1):
        table_name = table.get("table_name", f"table[{table_idx}]")
        if not table.get("table_id"):
            errors.append(f"{table_name}: table_id 누락")
        if not table.get("columns"):
            errors.append(f"{table_name}: columns 누락")
        if not any(column.get("pk") == "Y" for column in table.get("columns", [])):
            errors.append(f"{table_name}: PK 컬럼이 없습니다.")

    return errors


def load_db_inputs_node(state: DatabaseDesignWorkflowState) -> DatabaseDesignWorkflowState:
    requirement_json_path = state.get("requirement_json_path") or REQ_JSON_PATH
    requirement_data = _load_requirement(requirement_json_path=requirement_json_path)

    erd_docx_path = resolve_erd_docx_path(state.get("erd_docx_path"))
    erd = parse_erd_docx(erd_docx_path)

    return {
        "requirement_json_path": requirement_json_path,
        "erd_docx_path": erd_docx_path,
        "erd": erd,
        **requirement_data,
    }


def build_database_design_node(state: DatabaseDesignWorkflowState) -> DatabaseDesignWorkflowState:
    design = build_database_design(state["erd"])
    system_context = state["system_context"]

    design["requirement_id"] = system_context.get("requirement_id", "")
    design["requirement_name"] = system_context.get("requirement_name", "")
    design["requirement_ids"] = system_context.get("requirement_ids", [])
    design["requirement_count"] = system_context.get("requirement_count", 0)
    design["requirement_summary"] = system_context.get("description", "")

    if not design.get("system_name"):
        design["system_name"] = system_context.get("system_name", "") or "업무 시스템"

    return {"database_design": design}


def build_database_rag_context_node(state: DatabaseDesignWorkflowState) -> DatabaseDesignWorkflowState:
    if not state.get("use_rag", True):
        return {"rag_context": {}}

    rag_context = build_database_design_rag_context(state["database_design"])
    return {"rag_context": rag_context}


def enhance_database_design_node(state: DatabaseDesignWorkflowState) -> DatabaseDesignWorkflowState:
    if not state.get("use_rag", True) or not state.get("rag_context"):
        return {"database_design": state["database_design"]}

    return {
        "database_design": enhance_database_design_with_rag(
            state["database_design"],
            state["rag_context"],
        )
    }


def validate_database_design_node(state: DatabaseDesignWorkflowState) -> DatabaseDesignWorkflowState:
    errors = _validate_database_design(state.get("database_design") or {})
    if errors:
        return {"validation_errors": errors, "status": "INVALID"}
    return {"validation_errors": [], "status": "VALID"}


def save_database_design_json_node(state: DatabaseDesignWorkflowState) -> DatabaseDesignWorkflowState:
    output_json_path = state.get("output_json_path") or OUTPUT_JSON_PATH
    Path(output_json_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(state["database_design"], f, ensure_ascii=False, indent=2)
    return {"output_json_path": output_json_path}


def generate_database_design_docx_node(state: DatabaseDesignWorkflowState) -> DatabaseDesignWorkflowState:
    output_docx_path = state.get("output_docx_path") or OUTPUT_PATH
    saved_path = generate_database_design_docx(
        state["database_design"],
        output_path=output_docx_path,
    )
    return {
        "database_design_docx_path": saved_path,
        "output_docx_path": output_docx_path,
    }


def route_after_db_validation(state: DatabaseDesignWorkflowState) -> str:
    if state.get("status") == "VALID":
        return "save_database_design_json_node"
    return END


def compile_database_design_graph():
    workflow = StateGraph(DatabaseDesignWorkflowState)

    workflow.add_node("load_db_inputs_node", load_db_inputs_node)
    workflow.add_node("build_database_design_node", build_database_design_node)
    workflow.add_node("build_database_rag_context_node", build_database_rag_context_node)
    workflow.add_node("enhance_database_design_node", enhance_database_design_node)
    workflow.add_node("validate_database_design_node", validate_database_design_node)
    workflow.add_node("save_database_design_json_node", save_database_design_json_node)
    workflow.add_node("generate_database_design_docx_node", generate_database_design_docx_node)

    workflow.add_edge(START, "load_db_inputs_node")
    workflow.add_edge("load_db_inputs_node", "build_database_design_node")
    workflow.add_edge("build_database_design_node", "build_database_rag_context_node")
    workflow.add_edge("build_database_rag_context_node", "enhance_database_design_node")
    workflow.add_edge("enhance_database_design_node", "validate_database_design_node")
    workflow.add_conditional_edges(
        "validate_database_design_node",
        route_after_db_validation,
        {
            "save_database_design_json_node": "save_database_design_json_node",
            END: END,
        },
    )
    workflow.add_edge("save_database_design_json_node", "generate_database_design_docx_node")
    workflow.add_edge("generate_database_design_docx_node", END)

    return workflow.compile()
