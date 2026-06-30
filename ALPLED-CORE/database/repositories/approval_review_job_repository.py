from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models.approval_review_job import ApprovalReviewJob


TERMINAL_REVIEW_JOB_STATUSES = {"SUCCEEDED", "FAILED", "CANCELED"}


class ApprovalReviewJobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        job_id: str,
        docs_aprv_sn: int,
        docs_sn: int,
        approval_request_docs_dtl_sn: int,
        request_json: dict[str, Any],
        request_id: str | None,
    ) -> ApprovalReviewJob:
        job = ApprovalReviewJob(
            job_id=job_id,
            docs_aprv_sn=docs_aprv_sn,
            docs_sn=docs_sn,
            approval_request_docs_dtl_sn=approval_request_docs_dtl_sn,
            job_stts_cd="QUEUED",
            progress_rate=0,
            message_cn="정합성 검증 작업 대기 중입니다.",
            request_json=request_json,
            request_id=request_id,
            active_key=str(docs_aprv_sn),
        )
        self.session.add(job)
        self.session.flush()
        return job

    def find_by_job_id(self, job_id: str) -> ApprovalReviewJob | None:
        return self.session.scalar(
            select(ApprovalReviewJob).where(ApprovalReviewJob.job_id == job_id)
        )

    def find_active(
        self,
        docs_aprv_sn: int,
    ) -> ApprovalReviewJob | None:
        return self.session.scalar(
            select(ApprovalReviewJob)
            .where(
                ApprovalReviewJob.docs_aprv_sn == docs_aprv_sn,
                ApprovalReviewJob.job_stts_cd.in_(("QUEUED", "RUNNING")),
            )
            .order_by(ApprovalReviewJob.job_sn.desc())
            .limit(1)
        )

    def claim_next(self, worker_id: str) -> ApprovalReviewJob | None:
        job = self.session.scalar(
            select(ApprovalReviewJob)
            .where(ApprovalReviewJob.job_stts_cd == "QUEUED")
            .order_by(ApprovalReviewJob.requested_dt, ApprovalReviewJob.job_sn)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            return None
        now = datetime.now()
        job.job_stts_cd = "RUNNING"
        job.job_step_cd = "LOADING"
        job.progress_rate = 5
        job.message_cn = "검증 대상 산출물을 불러오고 있습니다."
        job.worker_id = worker_id
        job.started_dt = now
        job.heartbeat_dt = now
        self.session.flush()
        return job

    def update_progress(
        self,
        job_id: str,
        *,
        step: str,
        progress: int,
        message: str,
    ) -> None:
        job = self.find_by_job_id(job_id)
        if job is None or job.job_stts_cd in TERMINAL_REVIEW_JOB_STATUSES:
            return
        job.job_step_cd = step
        job.progress_rate = max(job.progress_rate, min(max(progress, 0), 99))
        job.message_cn = message
        job.heartbeat_dt = datetime.now()
        self.session.flush()

    def touch_heartbeat(self, job_id: str) -> None:
        job = self.find_by_job_id(job_id)
        if job is not None and job.job_stts_cd == "RUNNING":
            job.heartbeat_dt = datetime.now()
            self.session.flush()

    def update_snapshots(
        self,
        job_id: str,
        *,
        before_docs_dtl_sn: int,
        after_docs_dtl_sn: int,
        before_data: Any,
        after_data: Any,
    ) -> None:
        job = self.find_by_job_id(job_id)
        if job is None or job.job_stts_cd in TERMINAL_REVIEW_JOB_STATUSES:
            return
        job.before_docs_dtl_sn = before_docs_dtl_sn
        job.after_docs_dtl_sn = after_docs_dtl_sn
        job.before_data_json = before_data
        job.after_data_json = after_data
        job.heartbeat_dt = datetime.now()
        self.session.flush()

    def mark_succeeded(self, job_id: str, result: dict[str, Any]) -> None:
        job = self.find_by_job_id(job_id)
        if job is None:
            return
        now = datetime.now()
        job.job_stts_cd = "SUCCEEDED"
        job.job_step_cd = "COMPLETED"
        job.progress_rate = 100
        job.message_cn = "정합성 검증이 완료되었습니다."
        job.result_json = result
        job.error_cd = None
        job.error_msg = None
        job.completed_dt = now
        job.heartbeat_dt = now
        job.active_key = None
        self.session.flush()

    def mark_failed(self, job_id: str, error_code: str, error_message: str) -> None:
        job = self.find_by_job_id(job_id)
        if job is None:
            return
        now = datetime.now()
        job.job_stts_cd = "FAILED"
        job.message_cn = "정합성 검증에 실패했습니다."
        job.error_cd = error_code
        job.error_msg = error_message
        job.completed_dt = now
        job.heartbeat_dt = now
        job.active_key = None
        self.session.flush()
