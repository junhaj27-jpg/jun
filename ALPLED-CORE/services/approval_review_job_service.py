from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agents.approval_review.schemas import ApprovalReviewRequest
from agents.approval_review.repository import ApprovalReviewRepository
from database.models.approval_review_job import ApprovalReviewJob
from database.repositories.approval_review_job_repository import (
    ApprovalReviewJobRepository,
)


class ActiveApprovalReviewJobError(Exception):
    def __init__(self, job: ApprovalReviewJob) -> None:
        super().__init__("동일한 산출물의 정합성 검증 작업이 이미 진행 중입니다.")
        self.job = job


def create_approval_review_job(
    session: Session,
    request: ApprovalReviewRequest,
    *,
    request_id: str | None,
) -> ApprovalReviewJob:
    repository = ApprovalReviewJobRepository(session)
    approval = ApprovalReviewRepository(session).get_approval_request(
        request.docs_aprv_sn
    )
    if approval is None:
        raise LookupError(
            f"tbl_docs_approve row not found: docs_aprv_sn={request.docs_aprv_sn}"
        )
    active_job = repository.find_active(
        request.docs_aprv_sn,
    )
    if active_job is not None:
        raise ActiveApprovalReviewJobError(active_job)

    try:
        job = repository.create(
            job_id=str(uuid4()),
            docs_aprv_sn=request.docs_aprv_sn,
            docs_sn=int(approval["docs_sn"]),
            approval_request_docs_dtl_sn=int(
                approval["approval_request_docs_dtl_sn"]
            ),
            request_json=jsonable_encoder(request.model_dump(mode="json")),
            request_id=request_id,
        )
        session.commit()
        session.refresh(job)
        return job
    except IntegrityError as exc:
        session.rollback()
        active_job = repository.find_active(
            request.docs_aprv_sn,
        )
        if active_job is not None:
            raise ActiveApprovalReviewJobError(active_job) from exc
        raise


def build_approval_review_status(job: ApprovalReviewJob) -> dict:
    error = None
    if job.error_cd or job.error_msg:
        error = {
            "code": job.error_cd or "APPROVAL_REVIEW_FAILED",
            "message": job.error_msg or "정합성 검증에 실패했습니다.",
        }
    return {
        "job_id": job.job_id,
        "docs_aprv_sn": job.docs_aprv_sn,
        "docs_sn": job.docs_sn,
        "approval_request_docs_dtl_sn": job.approval_request_docs_dtl_sn,
        "before_docs_dtl_sn": job.before_docs_dtl_sn,
        "after_docs_dtl_sn": job.after_docs_dtl_sn,
        "before_data": job.before_data_json,
        "after_data": job.after_data_json,
        "status": job.job_stts_cd,
        "step": job.job_step_cd,
        "progress": job.progress_rate,
        "message": job.message_cn,
        "requested_at": job.requested_dt,
        "started_at": job.started_dt,
        "completed_at": job.completed_dt,
        "result": job.result_json,
        "error": error,
    }
