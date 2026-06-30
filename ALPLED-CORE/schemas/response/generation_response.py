from pydantic import BaseModel, ConfigDict

from schemas.common.common_schema import DocsCode
from schemas.response.generation_job_response import JobStatus


class GenerationResponse(BaseModel):
    """산출물 생성 작업 접수 응답입니다."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    project_sn: int
    docs_cd: DocsCode
    status: JobStatus
    status_url: str
    message: str | None = None
