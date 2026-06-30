from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from agents.approval_review.repository import ApprovalReviewRepository
from agents.approval_review.schemas import (
    ApprovalReviewAcceptedResponse,
    ApprovalReviewJobStatusResponse,
    ApprovalReviewRequest,
)
from config.logging_config import get_logger
from database.repositories.approval_review_job_repository import (
    ApprovalReviewJobRepository,
)
from database.session import get_db_session
from services.approval_review_job_service import (
    ActiveApprovalReviewJobError,
    build_approval_review_status,
    create_approval_review_job,
)


router = APIRouter(tags=["approval-review"])
logger = get_logger("api.approval_review_router")


@router.post(
    "/approval-review",
    response_model=ApprovalReviewAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_approval_review(
    request: ApprovalReviewRequest,
    http_request: Request,
    session: Session = Depends(get_db_session),
) -> ApprovalReviewAcceptedResponse:
    repository = ApprovalReviewRepository(session)
    approval = repository.get_approval_request(request.docs_aprv_sn)
    if approval is None:
        raise HTTPException(status_code=404, detail="승인 요청 정보를 찾을 수 없습니다.")

    request_id = getattr(http_request.state, "request_id", "-")
    try:
        job = create_approval_review_job(
            session,
            request,
            request_id=request_id,
        )
    except ActiveApprovalReviewJobError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "APPROVAL_REVIEW_JOB_ALREADY_ACTIVE",
                "message": str(exc),
                "job_id": exc.job.job_id,
                "status_url": f"/approval-review-jobs/{exc.job.job_id}",
            },
        ) from exc

    return ApprovalReviewAcceptedResponse(
        job_id=job.job_id,
        docs_aprv_sn=job.docs_aprv_sn,
        docs_sn=job.docs_sn,
        approval_request_docs_dtl_sn=job.approval_request_docs_dtl_sn,
        status="QUEUED",
        status_url=f"/approval-review-jobs/{job.job_id}",
        message="정합성 검증 작업이 접수되었습니다.",
    )


@router.get(
    "/approval-review-jobs/{job_id}",
    response_model=ApprovalReviewJobStatusResponse,
)
def get_approval_review_job(
    job_id: str,
    session: Session = Depends(get_db_session),
) -> ApprovalReviewJobStatusResponse:
    job = ApprovalReviewJobRepository(session).find_by_job_id(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당 정합성 검증 작업을 찾을 수 없습니다.",
        )
    return ApprovalReviewJobStatusResponse.model_validate(
        build_approval_review_status(job)
    )
