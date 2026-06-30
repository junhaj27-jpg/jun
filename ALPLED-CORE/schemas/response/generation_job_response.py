from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from schemas.common.common_schema import DocsCode


JobStatus = Literal[
    "PRGRS_PENDING",
    "PRGRS_PROCESSING",
    "PRGRS_COMPLETED",
    "PRGRS_FAILED",
]


class GenerationJobError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class GenerationJobStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    project_sn: int
    docs_cd: DocsCode
    status: JobStatus
    progress: int
    requested_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: GenerationJobError | None = None
