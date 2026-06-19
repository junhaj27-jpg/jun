from fastapi import APIRouter, status
from fastapi.concurrency import run_in_threadpool

from schemas.request.generation_request import GenerationRequest
from schemas.response.generation_response import GenerationResponse
from workflow.graph import workflow


router = APIRouter(tags=["generation"])


@router.post(
    "/generate",
    response_model=GenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate(request: GenerationRequest) -> GenerationResponse:
    """산출물 생성 워크플로우를 실행합니다."""

    state = request.model_dump(mode="json")
    result_state = await run_in_threadpool(workflow.invoke, state)
    response_result = {
        "next_action": result_state.get("next_action"),
        "final_document_json": result_state.get("final_document_json"),
        "export_result": result_state.get("export_result"),
        "validation_result": result_state.get("validation_result"),
        "cleanup_result": result_state.get("cleanup_result"),
        "warnings": result_state.get("warnings", []),
        "errors": result_state.get("errors", []),
    }
    if request.etc.get("debug"):
        response_result["agent_outputs"] = result_state.get("agent_outputs", {})

    return GenerationResponse(
        project_sn=result_state["project_sn"],
        docs_cd=result_state["docs_cd"],
        status=result_state["status"],
        message="Generation workflow finished.",
        result=response_result,
    )
