# 워크플로우 성공/실패와 무관하게 로컬 임시 리소스를 정리하는 노드입니다.

from collections.abc import Callable
from dataclasses import dataclass

from config.logging_config import get_logger
from config.logging_context import bind_state_log_extra
from config.settings import Settings
from tools.result import ToolResult
from tools.storage.cleanup_manager import cleanup_workflow_resources
from workflow.state import WorkflowState


logger = get_logger("workflow.nodes.cleanup_node")


@dataclass(frozen=True)
class CleanupDependencies:
    cleanup_manager: Callable[..., ToolResult] = cleanup_workflow_resources
    settings: Settings | None = None


def cleanup_node(
    state: WorkflowState,
    dependencies: CleanupDependencies | None = None,
) -> WorkflowState:
    """최종 산출물은 보존하고 workflow 임시 파일만 정리합니다."""

    dependencies = dependencies or CleanupDependencies()
    logger.info(
        "Cleanup started",
        extra=bind_state_log_extra(state, "cleanup_start"),
    )
    result = dependencies.cleanup_manager(state, settings=dependencies.settings)
    state["cleanup_result"] = result["data"] if result["success"] else result["error"]
    if not result["success"]:
        state["warnings"] = list(state.get("warnings", []))
        error = result.get("error") or {}
        state["warnings"].append(
            {
                "code": error.get("code", "CLEANUP_FAILED"),
                "message": error.get("message", "임시 파일 정리에 실패했습니다."),
                "details": error.get("details"),
            }
        )
        logger.warning(
            "Cleanup completed with warnings",
            extra=bind_state_log_extra(state, "cleanup_failed"),
        )
    else:
        logger.info(
            "Cleanup completed",
            extra=bind_state_log_extra(state, "cleanup_complete"),
        )
    return state
