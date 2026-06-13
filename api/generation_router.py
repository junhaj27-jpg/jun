from fastapi import APIRouter, status

from schemas.request.generation_request import GenerationRequest
from schemas.response.generation_response import GenerationResponse


router = APIRouter(tags=["generation"])


@router.post(
    "/generate",
    response_model=GenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate(request: GenerationRequest) -> GenerationResponse:
    """산출물 생성 요청을 접수하는 최소 stub 엔드포인트입니다."""

    return GenerationResponse(
        project_sn=request.project_sn,
        docs_cd=request.docs_cd,
        status="READY",
        message="Generation request accepted.",
    )
