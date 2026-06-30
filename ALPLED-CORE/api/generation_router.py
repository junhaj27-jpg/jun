import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from config.constants import GenerationJobStatus, normalize_docs_cd
from config.logging_config import get_logger
from config.logging_context import bind_log_extra
from database.repositories.generation_job_repository import GenerationJobRepository
from database.session import get_db_session
from schemas.request.generation_request import GenerationRequest
from schemas.response.generation_job_response import GenerationJobStatusResponse
from schemas.response.generation_response import GenerationResponse
from services.generation_job_service import (
    ActiveGenerationJobError,
    build_status_response,
    create_generation_job,
)


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
    session: Session = Depends(get_db_session),
) -> GenerationResponse:
    """산출물 생성 작업을 접수하고 즉시 Job ID를 반환합니다."""

    request_id = getattr(http_request.state, "request_id", "-")
    logger.info(
        "Generate request received payload=%s",
        json.dumps(
            request_body.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        extra=bind_log_extra(
            "generate_request_received",
            request_id=request_id,
            project_sn=request_body.project_sn,
            docs_cd=request_body.docs_cd,
        ),
    )
    try:
        job = create_generation_job(
            session,
            request_body,
            request_id=request_id,
        )
    except ActiveGenerationJobError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "GENERATION_JOB_ALREADY_ACTIVE",
                "message": str(exc),
                "job_id": exc.job.job_id,
                "status_url": f"/generation-jobs/{exc.job.job_id}",
            },
        ) from exc

    logger.info(
        "Generation job accepted job_id=%s",
        job.job_id,
        extra=bind_log_extra(
            "generate_job_accepted",
            request_id=request_id,
            project_sn=job.prj_sn,
            docs_cd=job.docs_cd,
        ),
    )

    return GenerationResponse(
        job_id=job.job_id,
        project_sn=job.prj_sn,
        docs_cd=normalize_docs_cd(job.docs_cd),
        status=GenerationJobStatus.PENDING.value,
        status_url=f"/generation-jobs/{job.job_id}",
        message="산출물 생성 작업이 접수되었습니다.",
    )


@router.get(
    "/generation-jobs/{job_id}",
    response_model=GenerationJobStatusResponse,
)
def get_generation_job(
    job_id: str,
    session: Session = Depends(get_db_session),
) -> GenerationJobStatusResponse:
    """Job ID로 산출물 생성 작업 상태를 조회합니다."""

    job = GenerationJobRepository(session).find_by_job_id(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당 생성 작업을 찾을 수 없습니다.",
        )
    return GenerationJobStatusResponse.model_validate(build_status_response(job))
