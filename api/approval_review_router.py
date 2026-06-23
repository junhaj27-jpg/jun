from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agents.approval_review.agent import ApprovalReviewAgent
from agents.approval_review.repository import ApprovalReviewRepository
from agents.approval_review.schemas import (
    ApprovalReviewRequest,
    ApprovalReviewResponse,
)
from config.logging_config import get_logger
from database.session import get_db_session


router = APIRouter(tags=["approval-review"])
logger = get_logger("api.approval_review_router")


@router.post("/approval-review", response_model=ApprovalReviewResponse)
def start_approval_review(
    request: ApprovalReviewRequest,
    session: Session = Depends(get_db_session),
) -> ApprovalReviewResponse:
    repository = ApprovalReviewRepository(session)
    if repository.get_docs(request.docs_sn) is None:
        raise HTTPException(status_code=404, detail="검토 대상 산출물이 없습니다.")
    if repository.get_docs_detail(
        request.docs_sn, request.approval_request_docs_dtl_sn
    ) is None:
        raise HTTPException(status_code=404, detail="승인 요청 상세 산출물이 없습니다.")

    try:
        result = ApprovalReviewAgent(repository).execute(
            request.docs_sn,
            request.approval_request_docs_dtl_sn,
        )
    except Exception as exc:
        logger.exception(
            "Approval artifact review failed docs_sn=%s docs_dtl_sn=%s",
            request.docs_sn,
            request.approval_request_docs_dtl_sn,
        )
        raise HTTPException(
            status_code=500,
            detail=f"산출물 검토 처리에 실패했습니다: {exc}",
        ) from exc
    return ApprovalReviewResponse.model_validate(result)
