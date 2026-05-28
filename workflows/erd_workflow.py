import json
from pathlib import Path
from typing import Any, Dict, List

from langgraph.graph import END, START, StateGraph

from agents.erd_agent import (
    REQ_JSON_PATH,
    build_erd_rag_context,
    call_qwen_for_erd,
    fallback_rule_based_erd,
)
from generators.erd_docx_generator import OUTPUT_PATH, generate_erd_docx, generate_mermaid_erd
from workflows.erd_state import ErdWorkflowState


MAX_RETRIES = 2
DEFAULT_OUTPUT_JSON_PATH = "./json_temp/erd_agent_output.json"


def _join_list(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value if item)
    return str(value or "")


def build_system_context(requirement_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Create one system-level context object for ERD/DB design."""
    requirements = requirement_doc.get("requirements", [])
    if not requirements:
        raise ValueError("requirements가 비어 있습니다.")

    requirement_ids = [item.get("requirement_id", "") for item in requirements if item.get("requirement_id")]
    requirement_names = [item.get("requirement_name", "") for item in requirements if item.get("requirement_name")]

    sections = []
    validation_sections = []
    constraint_sections = []
    source_sections = []
    for item in requirements:
        req_id = item.get("requirement_id", "")
        req_name = item.get("requirement_name", "")
        prefix = f"[{req_id}] {req_name}".strip()
        sections.append(f"{prefix}\n{item.get('description', '')}".strip())
        validation_sections.append(f"{prefix}\n{_join_list(item.get('validation_criteria', []))}".strip())
        constraint_sections.append(f"{prefix}\n{_join_list(item.get('constraints', []))}".strip())
        source_sections.append(f"{prefix}\n{_join_list(item.get('source', []))}".strip())

    return {
        "requirement_id": "SYSTEM-ALL",
        "requirement_name": "전체 요구사항 기반 통합 ERD",
        "requirement_type": "통합",
        "description": "\n\n".join(section for section in sections if section),
        "source": source_sections,
        "constraints": constraint_sections,
        "priority": "통합",
        "validation_criteria": validation_sections,
        "note": requirement_doc.get("note", ""),
        "requirement_ids": requirement_ids,
        "requirement_names": requirement_names,
        "requirement_count": len(requirements),
    }


def _required_text(value: Any) -> bool:
    return bool(str(value or "").strip())


def _validate_erd(erd: Dict[str, Any]) -> List[str]:
    errors = []
    required_top_fields = ["system_name", "erd_id", "erd_name", "requirement_id", "entities"]

    for field in required_top_fields:
        if not erd.get(field):
            errors.append(f"필수 필드 누락: {field}")

    entities = erd.get("entities", [])
    if not isinstance(entities, list) or not entities:
        errors.append("entities는 1개 이상이어야 합니다.")
        return errors

    entity_names = set()

    for entity_idx, entity in enumerate(entities, start=1):
        entity_name = entity.get("entity_name", "")

        if not _required_text(entity_name):
            errors.append(f"ENT-{entity_idx:03d}: entity_name 누락")
        else:
            entity_names.add(entity_name)

        columns = entity.get("columns", [])
        if not isinstance(columns, list) or not columns:
            errors.append(f"{entity_name or entity_idx}: columns는 1개 이상이어야 합니다.")
            continue

        if not any(col.get("pk") == "Y" for col in columns):
            errors.append(f"{entity_name}: PK 컬럼이 없습니다.")

        for col_idx, col in enumerate(columns, start=1):
            for field in ["name", "synonym", "type"]:
                if not _required_text(col.get(field)):
                    errors.append(f"{entity_name}.{col_idx}: 컬럼 필수 필드 누락: {field}")

    for rel_idx, rel in enumerate(erd.get("relationships", []), start=1):
        from_entity = rel.get("from_entity", "")
        to_entity = rel.get("to_entity", "")

        if from_entity and from_entity not in entity_names:
            errors.append(f"relationship[{rel_idx}] from_entity가 entities에 없습니다: {from_entity}")
        if to_entity and to_entity not in entity_names:
            errors.append(f"relationship[{rel_idx}] to_entity가 entities에 없습니다: {to_entity}")

    return errors


def normalize_erd_entities(erd: Dict[str, Any]) -> Dict[str, Any]:
    entities = erd.get("entities", [])
    if not isinstance(entities, list):
        return erd

    for idx, entity in enumerate(entities, start=1):
        if not isinstance(entity, dict):
            continue

        entity_id = str(entity.get("entity_id") or "").strip()
        if not entity_id or entity_id.upper() in {"ALL", "SYSTEM-ALL"}:
            entity["entity_id"] = f"ENT-{idx:03d}"

        entity_name = str(entity.get("entity_name") or "").strip()
        if not entity_name:
            fallback_name = entity.get("table_name") or entity.get("name") or f"ENTITY_{idx:03d}"
            entity["entity_name"] = str(fallback_name).strip()

    return erd


def load_requirement_node(state: ErdWorkflowState) -> ErdWorkflowState:
    requirement_json_path = state.get("requirement_json_path") or REQ_JSON_PATH
    with open(requirement_json_path, "r", encoding="utf-8") as f:
        requirement_doc = json.load(f)

    system_context = build_system_context(requirement_doc)

    return {
        "requirement_json_path": requirement_json_path,
        "requirement_doc": requirement_doc,
        "system_context": system_context,
        "retry_count": state.get("retry_count", 0),
    }


def build_erd_rag_context_node(state: ErdWorkflowState) -> ErdWorkflowState:
    rag_context = build_erd_rag_context(state["system_context"])
    return {"rag_context": rag_context}


def generate_erd_candidate_node(state: ErdWorkflowState) -> ErdWorkflowState:
    use_llm = state.get("use_llm", True)
    if use_llm:
        try:
            erd = call_qwen_for_erd(state["system_context"], state["rag_context"])
            return {"erd": normalize_erd_entities(erd), "status": "GENERATED_BY_LLM"}
        except Exception as exc:
            return {
                "validation_errors": [f"LLM ERD 생성 실패: {exc}"],
                "status": "LLM_FAILED",
            }

    return {
        "erd": normalize_erd_entities(fallback_rule_based_erd(state["system_context"])),
        "status": "GENERATED_BY_RULE",
    }


def repair_erd_node(state: ErdWorkflowState) -> ErdWorkflowState:
    retry_count = state.get("retry_count", 0) + 1
    erd = normalize_erd_entities(fallback_rule_based_erd(state["system_context"]))
    return {
        "erd": erd,
        "retry_count": retry_count,
        "status": "REPAIRED_BY_RULE",
    }


def validate_erd_node(state: ErdWorkflowState) -> ErdWorkflowState:
    erd = state.get("erd") or {}
    errors = _validate_erd(erd)
    if errors:
        return {"validation_errors": errors, "status": "INVALID"}
    return {"validation_errors": [], "status": "VALID"}


def generate_mermaid_node(state: ErdWorkflowState) -> ErdWorkflowState:
    return {"mermaid_script": generate_mermaid_erd(state["erd"])}


def save_erd_json_node(state: ErdWorkflowState) -> ErdWorkflowState:
    output_json_path = state.get("output_json_path") or DEFAULT_OUTPUT_JSON_PATH
    Path(output_json_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(state["erd"], f, ensure_ascii=False, indent=2)
    return {"output_json_path": output_json_path}


def generate_erd_docx_node(state: ErdWorkflowState) -> ErdWorkflowState:
    output_docx_path = state.get("output_docx_path") or OUTPUT_PATH
    saved_path = generate_erd_docx(
        state["erd"],
        output_path=output_docx_path,
        use_mermaid=state.get("use_mermaid", True),
        fast_table=state.get("fast_table", False),
    )
    return {"erd_docx_path": saved_path, "output_docx_path": output_docx_path}


def route_after_generation(state: ErdWorkflowState) -> str:
    if state.get("erd"):
        return "validate_erd_node"
    return "repair_erd_node"


def route_after_validation(state: ErdWorkflowState) -> str:
    if state.get("status") == "VALID":
        return "generate_mermaid_node"
    if state.get("retry_count", 0) < MAX_RETRIES:
        return "repair_erd_node"
    return END


def compile_erd_graph():
    workflow = StateGraph(ErdWorkflowState)

    workflow.add_node("load_requirement_node", load_requirement_node)
    workflow.add_node("build_erd_rag_context_node", build_erd_rag_context_node)
    workflow.add_node("generate_erd_candidate_node", generate_erd_candidate_node)
    workflow.add_node("repair_erd_node", repair_erd_node)
    workflow.add_node("validate_erd_node", validate_erd_node)
    workflow.add_node("generate_mermaid_node", generate_mermaid_node)
    workflow.add_node("save_erd_json_node", save_erd_json_node)
    workflow.add_node("generate_erd_docx_node", generate_erd_docx_node)

    workflow.add_edge(START, "load_requirement_node")
    workflow.add_edge("load_requirement_node", "build_erd_rag_context_node")
    workflow.add_edge("build_erd_rag_context_node", "generate_erd_candidate_node")
    workflow.add_conditional_edges(
        "generate_erd_candidate_node",
        route_after_generation,
        {
            "validate_erd_node": "validate_erd_node",
            "repair_erd_node": "repair_erd_node",
        },
    )
    workflow.add_edge("repair_erd_node", "validate_erd_node")
    workflow.add_conditional_edges(
        "validate_erd_node",
        route_after_validation,
        {
            "generate_mermaid_node": "generate_mermaid_node",
            "repair_erd_node": "repair_erd_node",
            END: END,
        },
    )
    workflow.add_edge("generate_mermaid_node", "save_erd_json_node")
    workflow.add_edge("save_erd_json_node", "generate_erd_docx_node")
    workflow.add_edge("generate_erd_docx_node", END)

    return workflow.compile()
