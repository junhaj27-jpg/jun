import json

from fastapi import APIRouter, Request, status
from fastapi.concurrency import run_in_threadpool

from config.logging_config import get_logger
from config.logging_context import bind_log_extra
from schemas.request.generation_request import GenerationRequest
from schemas.response.generation_response import GenerationResponse
from workflow.graph import workflow


router = APIRouter(tags=["generation"])
logger = get_logger("api.generation_router")


@router.post(
    "/generate",
    response_model=GenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate(
    request_body: GenerationRequest,
    http_request: Request,
) -> GenerationResponse:
    """산출물 생성 워크플로우를 실행합니다."""

    request_id = getattr(http_request.state, "request_id", "-")
    state = request_body.model_dump(mode="json")
    state.setdefault("etc", {})
    state["etc"]["request_id"] = request_id

    logger.info(
        "Generate request received payload=%s",
        json.dumps(state, ensure_ascii=False, separators=(",", ":")),
        extra=bind_log_extra(
            "generate_request_received",
            request_id=request_id,
            project_sn=state.get("project_sn"),
            docs_cd=state.get("docs_cd"),
        ),
    )
    logger.info(
        "Invoking generation workflow",
        extra=bind_log_extra(
            "generate_workflow_invoke_start",
            request_id=request_id,
            project_sn=state.get("project_sn"),
            docs_cd=state.get("docs_cd"),
        ),
    )
    try:
        result_state = await run_in_threadpool(workflow.invoke, state)
    except Exception:
        logger.exception(
            "Generation workflow invocation failed",
            extra=bind_log_extra(
                "generate_workflow_invoke_failed",
                request_id=request_id,
                project_sn=state.get("project_sn"),
                docs_cd=state.get("docs_cd"),
            ),
        )
        raise
    logger.info(
        "Generation workflow invocation completed status=%s",
        result_state.get("status"),
        extra=bind_log_extra(
            "generate_workflow_invoke_complete",
            request_id=request_id,
            project_sn=result_state.get("project_sn"),
            docs_cd=result_state.get("docs_cd"),
        ),
    )
    response_result = {
        "next_action": result_state.get("next_action"),
        "final_document_json": result_state.get("final_document_json"),
        "export_result": result_state.get("export_result"),
        "validation_result": result_state.get("validation_result"),
        "cleanup_result": result_state.get("cleanup_result"),
        "warnings": result_state.get("warnings", []),
        "errors": result_state.get("errors", []),
    }
    if request_body.etc.get("debug"):
        response_result["agent_outputs"] = result_state.get("agent_outputs", {})
        response_result["repair_history"] = result_state.get("repair_history", [])

    return GenerationResponse(
        project_sn=result_state["project_sn"],
        docs_cd=result_state["docs_cd"],
        status=result_state["status"],
        message="Generation workflow finished.",
        result=response_result,
    )
