from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.constants import GenerationJobStatus
from database.models.generation_job import GenerationJob


ACTIVE_JOB_STATUSES = (
    GenerationJobStatus.PENDING.value,
    GenerationJobStatus.PROCESSING.value,
)
TERMINAL_JOB_STATUSES = {
    GenerationJobStatus.COMPLETED.value,
    GenerationJobStatus.FAILED.value,
}


class GenerationJobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        job_id: str,
        project_sn: int,
        docs_cd: str,
        request_json: dict[str, Any],
        request_id: str | None,
        docs_sn: int | None = None,
        max_retry_count: int = 1,
    ) -> GenerationJob:
        job = GenerationJob(
            job_id=job_id,
            prj_sn=project_sn,
            docs_cd=docs_cd,
            docs_sn=docs_sn,
            job_stts_cd=GenerationJobStatus.PENDING.value,
            progress_rate=0,
            request_json=request_json,
            request_id=request_id,
            retry_cnt=0,
            max_retry_cnt=max_retry_count,
            active_key=f"{project_sn}:{docs_cd}",
        )
        self.session.add(job)
        self.session.flush()
        return job

    def find_by_job_id(self, job_id: str) -> GenerationJob | None:
        return self.session.scalar(
            select(GenerationJob).where(GenerationJob.job_id == job_id)
        )

    def find_active(
        self,
        project_sn: int,
        docs_cd: str,
        *,
        legacy_docs_cd: str | None = None,
    ) -> GenerationJob | None:
        docs_codes = (
            (docs_cd, legacy_docs_cd)
            if legacy_docs_cd is not None and legacy_docs_cd != docs_cd
            else (docs_cd,)
        )
        return self.session.scalar(
            select(GenerationJob)
            .where(
                GenerationJob.prj_sn == project_sn,
                GenerationJob.docs_cd.in_(docs_codes),
                GenerationJob.job_stts_cd.in_(ACTIVE_JOB_STATUSES),
            )
            .order_by(GenerationJob.job_sn.desc())
            .limit(1)
        )

    def claim_next(self) -> GenerationJob | None:
        statement = (
            select(GenerationJob)
            .where(GenerationJob.job_stts_cd == GenerationJobStatus.PENDING.value)
            .order_by(GenerationJob.requested_dt, GenerationJob.job_sn)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        job = self.session.scalar(statement)
        if job is None:
            return None

        now = datetime.now()
        job.job_stts_cd = GenerationJobStatus.PROCESSING.value
        job.progress_rate = 5
        job.started_dt = job.started_dt or now
        job.heartbeat_dt = now
        self.session.flush()
        return job

    def recover_stale_jobs(self, stale_before: datetime) -> tuple[int, int]:
        jobs = self.session.scalars(
            select(GenerationJob)
            .where(
                GenerationJob.job_stts_cd == GenerationJobStatus.PROCESSING.value,
                GenerationJob.heartbeat_dt < stale_before,
            )
            .with_for_update(skip_locked=True)
        ).all()
        requeued = 0
        failed = 0
        for job in jobs:
            if job.retry_cnt < job.max_retry_cnt:
                job.retry_cnt += 1
                job.job_stts_cd = GenerationJobStatus.PENDING.value
                job.progress_rate = 0
                job.heartbeat_dt = None
                requeued += 1
                continue

            now = datetime.now()
            job.job_stts_cd = GenerationJobStatus.FAILED.value
            job.error_cd = "GENERATION_WORKER_STALE"
            job.error_msg = "작업 Worker의 heartbeat가 제한 시간 동안 갱신되지 않았습니다."
            job.completed_dt = now
            job.active_key = None
            failed += 1
        self.session.flush()
        return requeued, failed

    def update_progress(
        self,
        job_id: str,
        *,
        step: str,
        progress: int,
        message: str,
    ) -> GenerationJob | None:
        del step
        del message

        job = self.find_by_job_id(job_id)
        if job is None or job.job_stts_cd in TERMINAL_JOB_STATUSES:
            return job
        job.job_stts_cd = GenerationJobStatus.PROCESSING.value
        job.progress_rate = max(job.progress_rate, min(max(progress, 0), 99))
        job.heartbeat_dt = datetime.now()
        self.session.flush()
        return job

    def touch_heartbeat(self, job_id: str) -> None:
        job = self.find_by_job_id(job_id)
        if job is not None and job.job_stts_cd == GenerationJobStatus.PROCESSING.value:
            job.heartbeat_dt = datetime.now()
            self.session.flush()

    def mark_succeeded(
        self,
        job_id: str,
        result: dict[str, Any],
        *,
        docs_sn: int | None = None,
    ) -> GenerationJob | None:
        job = self.find_by_job_id(job_id)
        if job is None:
            return None
        now = datetime.now()
        job.job_stts_cd = GenerationJobStatus.COMPLETED.value
        job.progress_rate = 100
        job.result_json = result
        if docs_sn is not None:
            job.docs_sn = docs_sn
        job.error_cd = None
        job.error_msg = None
        job.completed_dt = now
        job.heartbeat_dt = now
        job.active_key = None
        self.session.flush()
        return job

    def mark_failed(
        self,
        job_id: str,
        *,
        error_code: str,
        error_message: str,
        result: dict[str, Any] | None = None,
    ) -> GenerationJob | None:
        job = self.find_by_job_id(job_id)
        if job is None:
            return None
        now = datetime.now()
        job.job_stts_cd = GenerationJobStatus.FAILED.value
        job.result_json = result
        job.error_cd = error_code
        job.error_msg = error_message
        job.completed_dt = now
        job.heartbeat_dt = now
        job.active_key = None
        self.session.flush()
        return job
