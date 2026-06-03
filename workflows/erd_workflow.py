import json
from typing import Any, Dict, List

from langgraph.graph import END, START, StateGraph

from agents.erd.erd_agent import (
    REQ_JSON_PATH,
    build_integrated_requirement,
    call_qwen_for_erd,
    fallback_rule_based_erd,
)
from generators.erd.docx_generator import OUTPUT_PATH, generate_erd_docx, generate_mermaid_erd
from common.services.document_loader_service import load_meeting_documents, load_requirement_document
from common.db.repositories.docs_repository import insert_docs_with_detail
from common.db.repositories.file_repository import insert_file_metadata
from agents.erd.erd_mapper import (
    build_entity_candidate_json,
    build_requirement_context,
    build_table_structure_json,
    normalize_final_erd_json,
)
from generators.erd.docx_adapter import final_erd_to_template_erd
from generators.erd.mermaid_generator import generate_mermaid_code, render_erd_image
from generators.erd.storage import build_erd_output_paths, save_erd_json, save_mermaid_code
from rag.erd_rag_service import build_erd_rag_context, search_erd_standards
from workflows.erd_state import ErdWorkflowState


MAX_RETRIES = 2
DEFAULT_OUTPUT_JSON_PATH = "./json_temp/erd_agent_output.json"

def build_system_context(requirement_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Create one system-level context object for ERD/DB design."""
    return build_integrated_requirement(requirement_doc)


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

        entity["entity_id"] = f"ENT-{idx:03d}"

        entity_name = str(entity.get("entity_name") or "").strip()
        if not entity_name:
            fallback_name = entity.get("table_name") or entity.get("name") or f"ENTITY_{idx:03d}"
            entity["entity_name"] = str(fallback_name).strip()

    return erd


def load_common_documents_node(state: ErdWorkflowState) -> ErdWorkflowState:
    if state.get("prj_sn") and (state.get("requirement_docs_sn") or state.get("requirement_file_sn")):
        requirement_doc = load_requirement_document(
            prj_sn=int(state["prj_sn"]),
            requirement_docs_sn=state.get("requirement_docs_sn"),
            requirement_file_sn=state.get("requirement_file_sn"),
        )
        meeting_docs = load_meeting_documents(
            prj_sn=int(state["prj_sn"]),
            meeting_file_sns=state.get("meeting_file_sns", []),
        )
        requirement_json = requirement_doc["requirement_json"]
        meeting_text = meeting_docs["merged_text"]

        return {
            "requirement_path": requirement_doc["file_path"],
            "meeting_file_paths": [item["file_path"] for item in meeting_docs["files"]],
            "requirement_text": requirement_doc["text"],
            "meeting_text": meeting_text,
            "requirement_json": requirement_json,
            "requirement_doc": requirement_json,
            "system_context": build_requirement_context(requirement_json, meeting_text),
            "retry_count": state.get("retry_count", 0),
            "save_to_db": state.get("save_to_db", True),
        }

    requirement_json_path = state.get("requirement_json_path") or REQ_JSON_PATH
    with open(requirement_json_path, "r", encoding="utf-8") as f:
        requirement_doc = json.load(f)

    system_context = build_system_context(requirement_doc)

    return {
        "requirement_json_path": requirement_json_path,
        "requirement_json": requirement_doc,
        "requirement_doc": requirement_doc,
        "system_context": system_context,
        "retry_count": state.get("retry_count", 0),
    }


def build_erd_rag_context_node(state: ErdWorkflowState) -> ErdWorkflowState:
    if state.get("requirement_json") or state.get("meeting_text"):
        return {
            "rag_context": search_erd_standards(
                state.get("requirement_json") or state.get("requirement_doc") or {},
                state.get("meeting_text", ""),
            )
        }
    rag_context = build_erd_rag_context(state["system_context"])
    return {"rag_context": rag_context}


def extract_table_candidates_node(state: ErdWorkflowState) -> ErdWorkflowState:
    table_structure_json = build_table_structure_json(
        state.get("requirement_json") or state.get("requirement_doc") or {},
        state.get("meeting_text", ""),
    )
    return {"table_structure_json": table_structure_json}


def generate_entity_candidate_node(state: ErdWorkflowState) -> ErdWorkflowState:
    return {"entity_candidate_json": build_entity_candidate_json(state.get("table_structure_json") or {})}


def generate_erd_candidate_node(state: ErdWorkflowState) -> ErdWorkflowState:
    use_llm = state.get("use_llm", True)
    system_context = dict(state["system_context"])
    system_context["table_structure_candidates"] = state.get("table_structure_json", {})
    system_context["entity_candidates"] = state.get("entity_candidate_json", {})

    if use_llm:
        try:
            erd = call_qwen_for_erd(system_context, state["rag_context"])
            return {"erd": normalize_erd_entities(erd), "status": "GENERATED_BY_LLM"}
        except Exception as exc:
            return {
                "validation_errors": [f"LLM ERD 생성 실패: {exc}"],
                "status": "LLM_FAILED",
            }

    return {
        "erd": normalize_erd_entities(fallback_rule_based_erd(system_context)),
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


def generate_final_erd_json_node(state: ErdWorkflowState) -> ErdWorkflowState:
    return {"final_erd_json": normalize_final_erd_json(state["erd"])}


def generate_mermaid_node(state: ErdWorkflowState) -> ErdWorkflowState:
    final_erd_json = state.get("final_erd_json")
    if final_erd_json:
        return {"mermaid_script": generate_mermaid_code(final_erd_json)}
    return {"mermaid_script": generate_mermaid_erd(state["erd"])}


def render_erd_image_node(state: ErdWorkflowState) -> ErdWorkflowState:
    prj_sn = state.get("prj_sn")
    paths = build_erd_output_paths(prj_sn=int(prj_sn) if prj_sn else None)
    output_json_path = state.get("output_json_path") or paths["json_path"]
    output_docx_path = state.get("output_docx_path") or paths["docx_path"]
    erd_image_path = state.get("erd_image_path") or paths["image_path"]
    mmd_path = paths["mmd_path"]
    final_erd_json = state.get("final_erd_json") or normalize_final_erd_json(state["erd"])
    mermaid_script = state.get("mermaid_script") or generate_mermaid_code(final_erd_json)

    image_path = render_erd_image(final_erd_json, mermaid_script, erd_image_path)
    save_mermaid_code(mermaid_script, mmd_path)

    return {
        "output_json_path": output_json_path,
        "output_docx_path": output_docx_path,
        "erd_image_path": image_path or "",
    }


def save_erd_json_node(state: ErdWorkflowState) -> ErdWorkflowState:
    output_json_path = state.get("output_json_path") or DEFAULT_OUTPUT_JSON_PATH
    save_erd_json(state.get("final_erd_json") or state["erd"], output_json_path)
    return {"output_json_path": output_json_path}


def generate_erd_docx_node(state: ErdWorkflowState) -> ErdWorkflowState:
    output_docx_path = state.get("output_docx_path") or OUTPUT_PATH
    erd_for_docx = final_erd_to_template_erd(state.get("final_erd_json") or state["erd"])
    saved_path = generate_erd_docx(
        erd_for_docx,
        output_path=output_docx_path,
        use_mermaid=state.get("use_mermaid", True) and not state.get("erd_image_path"),
        fast_table=state.get("fast_table", False),
        erd_image_path=state.get("erd_image_path") or None,
    )
    return {"erd_docx_path": saved_path, "output_docx_path": output_docx_path}


def insert_docs_db_node(state: ErdWorkflowState) -> ErdWorkflowState:
    if not state.get("prj_sn") or not state.get("save_to_db", False):
        return {"success": True}

    saved = insert_docs_with_detail(
        prj_sn=int(state["prj_sn"]),
        docs_cd="ERD",
        docs_ver="1.0",
        mdfcn_cn="ERD 설계서 자동 생성",
        docs_path=state["erd_docx_path"],
        login_user_sn=int(state["login_user_sn"]),
        pssn_user_sn=int(state["login_user_sn"]),
    )

    result: ErdWorkflowState = {
        "docs_sn": saved["docs_sn"],
        "docs_dtl_sn": saved["docs_dtl_sn"],
        "success": True,
    }

    if state.get("save_image_file", True) and state.get("erd_image_path"):
        image_saved = insert_file_metadata(
            prj_sn=int(state["prj_sn"]),
            file_cd="ERD_IMG",
            file_path=state["erd_image_path"],
            login_user_sn=int(state["login_user_sn"]),
        )
        result["erd_image_file_sn"] = image_saved["file_sn"]

    return result


def route_after_generation(state: ErdWorkflowState) -> str:
    if state.get("erd"):
        return "validate_erd_node"
    return "repair_erd_node"


def route_after_validation(state: ErdWorkflowState) -> str:
    if state.get("status") == "VALID":
        return "generate_final_erd_json_node"
    if state.get("retry_count", 0) < MAX_RETRIES:
        return "repair_erd_node"
    return END


def compile_erd_graph():
    workflow = StateGraph(ErdWorkflowState)

    workflow.add_node("load_common_documents_node", load_common_documents_node)
    workflow.add_node("extract_table_candidates_node", extract_table_candidates_node)
    workflow.add_node("generate_entity_candidate_node", generate_entity_candidate_node)
    workflow.add_node("build_erd_rag_context_node", build_erd_rag_context_node)
    workflow.add_node("generate_erd_candidate_node", generate_erd_candidate_node)
    workflow.add_node("repair_erd_node", repair_erd_node)
    workflow.add_node("validate_erd_node", validate_erd_node)
    workflow.add_node("generate_final_erd_json_node", generate_final_erd_json_node)
    workflow.add_node("generate_mermaid_node", generate_mermaid_node)
    workflow.add_node("render_erd_image_node", render_erd_image_node)
    workflow.add_node("save_erd_json_node", save_erd_json_node)
    workflow.add_node("generate_erd_docx_node", generate_erd_docx_node)
    workflow.add_node("insert_docs_db_node", insert_docs_db_node)

    workflow.add_edge(START, "load_common_documents_node")
    workflow.add_edge("load_common_documents_node", "extract_table_candidates_node")
    workflow.add_edge("extract_table_candidates_node", "generate_entity_candidate_node")
    workflow.add_edge("generate_entity_candidate_node", "build_erd_rag_context_node")
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
            "generate_final_erd_json_node": "generate_final_erd_json_node",
            "repair_erd_node": "repair_erd_node",
            END: END,
        },
    )
    workflow.add_edge("generate_final_erd_json_node", "generate_mermaid_node")
    workflow.add_edge("generate_mermaid_node", "render_erd_image_node")
    workflow.add_edge("render_erd_image_node", "save_erd_json_node")
    workflow.add_edge("save_erd_json_node", "generate_erd_docx_node")
    workflow.add_edge("generate_erd_docx_node", "insert_docs_db_node")
    workflow.add_edge("insert_docs_db_node", END)

    return workflow.compile()


def generate_erd_design_from_request(payload: dict[str, Any]) -> dict[str, Any]:
    result = compile_erd_graph().invoke(
        {
            "prj_sn": payload["prj_sn"],
            "requirement_docs_sn": payload.get("requirement_docs_sn"),
            "requirement_file_sn": payload.get("requirement_file_sn"),
            "meeting_file_sns": payload.get("meeting_file_sns", []),
            "login_user_sn": payload["login_user_sn"],
            "use_llm": payload.get("use_llm", True),
            "use_mermaid": payload.get("use_mermaid", True),
            "fast_table": payload.get("fast_table", False),
            "save_to_db": payload.get("save_to_db", True),
            "save_image_file": payload.get("save_image_file", True),
        }
    )

    if result.get("status") != "VALID":
        return {
            "success": False,
            "message": "ERD 설계서 생성 실패",
            "validation_errors": result.get("validation_errors", []),
        }

    return {
        "success": True,
        "docs_sn": result.get("docs_sn"),
        "docs_dtl_sn": result.get("docs_dtl_sn"),
        "docx_path": result.get("erd_docx_path"),
        "erd_image_path": result.get("erd_image_path"),
        "erd_image_file_sn": result.get("erd_image_file_sn"),
        "output_json_path": result.get("output_json_path"),
    }
