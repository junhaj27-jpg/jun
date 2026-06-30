from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config.constants import DOCS_CODE_DB_MAP, normalize_docs_cd
from database.models.generation_job import GenerationJob
from database.repositories.generation_job_repository import GenerationJobRepository
from schemas.request.generation_request import GenerationRequest


class ActiveGenerationJobError(Exception):
    def __init__(self, job: GenerationJob) -> None:
        super().__init__("동일한 프로젝트와 산출물의 생성 작업이 이미 진행 중입니다.")
        self.job = job


def create_generation_job(
    session: Session,
    request: GenerationRequest,
    *,
    request_id: str | None,
) -> GenerationJob:
    repository = GenerationJobRepository(session)
    api_docs_cd = str(request.docs_cd)
    db_docs_cd = DOCS_CODE_DB_MAP.get(api_docs_cd, api_docs_cd)
    active_job = repository.find_active(
        request.project_sn,
        db_docs_cd,
        legacy_docs_cd=api_docs_cd,
    )
    if active_job is not None:
        raise ActiveGenerationJobError(active_job)

    try:
        job = repository.create(
            job_id=str(uuid4()),
            project_sn=request.project_sn,
            docs_cd=db_docs_cd,
            docs_sn=request.docs_sn,
            request_json=jsonable_encoder(request.model_dump(mode="json")),
            request_id=request_id,
        )
        session.commit()
        session.refresh(job)
        return job
    except IntegrityError as exc:
        session.rollback()
        active_job = repository.find_active(
            request.project_sn,
            db_docs_cd,
            legacy_docs_cd=api_docs_cd,
        )
        if active_job is not None:
            raise ActiveGenerationJobError(active_job) from exc
        raise


def build_status_response(job: GenerationJob) -> dict:
    error = None
    if job.error_cd or job.error_msg:
        error = {
            "code": job.error_cd or "GENERATION_FAILED",
            "message": job.error_msg or "산출물 생성에 실패했습니다.",
        }

    return {
        "job_id": job.job_id,
        "project_sn": job.prj_sn,
        "docs_cd": normalize_docs_cd(job.docs_cd),
        "status": job.job_stts_cd,
        "progress": job.progress_rate,
        "requested_at": job.requested_dt,
        "started_at": job.started_dt,
        "completed_at": job.completed_dt,
        "result": job.result_json,
        "error": error,
    }
