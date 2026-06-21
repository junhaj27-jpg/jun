from config.logging_config import get_logger
from config.logging_context import bind_state_log_extra
from database.repositories.architecture_config_repository import (
    ArchitectureConfigRepository,
)
from database.session import SessionLocal
from supervisor.generation_supervisor import run_generation_supervisor
from supervisor.registry.agent_registry import build_default_agent_registry
from workflow.state import WorkflowState


logger = get_logger("workflow.nodes.generation_supervisor_node")


def generation_supervisor_node(state: WorkflowState) -> WorkflowState:
    debug = bool((state.get("etc") or {}).get("debug"))
    if debug and str(state.get("docs_cd", "")).upper() == "ARCH":
        print("[ARCH_TRACE][generation_supervisor_node] file:", __file__)
        print("[ARCH_TRACE][generation_supervisor_node] docs_cd:", state.get("docs_cd"))
        print("[ARCH_TRACE][generation_supervisor_node] udt_yn:", state.get("udt_yn"))
        print("[ARCH_TRACE][generation_supervisor_node] state keys:", list(state.keys()))

    logger.info(
        "Generation supervisor node started",
        extra=bind_state_log_extra(state, "supervisor_start"),
    )
    session = SessionLocal()
    try:
        registry = build_default_agent_registry(
            architecture_config_repository=ArchitectureConfigRepository(session),
        )
        result = run_generation_supervisor(state, registry)
        logger.info(
            "Generation supervisor node completed status=%s",
            result.get("status"),
            extra=bind_state_log_extra(result, "supervisor_complete"),
        )
        if debug and str(state.get("docs_cd", "")).upper() == "ARCH":
            print("[ARCH_TRACE][generation_supervisor_node] result status:", result.get("status"))
            print("[ARCH_TRACE][generation_supervisor_node] final_document_json exists:", bool(result.get("final_document_json")))
            print("[ARCH_TRACE][generation_supervisor_node] agent_outputs keys:", list((result.get("agent_outputs") or {}).keys()))
        return result
    finally:
        session.close()
