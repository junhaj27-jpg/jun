from datetime import datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


ReviewStatus = Literal["ok", "issues_found", "failed", "skipped"]
ApprovalReviewJobStatus = Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED"]


class ApprovalReviewRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    docs_aprv_sn: int = Field(
        gt=0,
        validation_alias=AliasChoices(
            "docs_aprv_sn",
            "docsAprvSn",
            "approve_sn",
            "approval_sn",
        ),
    )


class ApprovalReviewResponse(BaseModel):
    docs_aprv_sn: int | None = None
    status: ReviewStatus
    docs_sn: int
    target_docs_cd: str
    before_docs_dtl_sn: int
    after_docs_dtl_sn: int
    reference_requirement_docs_sn: int | None = None
    reference_requirement_docs_dtl_sn: int | None = None
    reference_requirement_file_sn: int | None = None
    change_review: dict[str, Any]
    consistency_check: dict[str, Any]


class ApprovalReviewAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    docs_aprv_sn: int
    docs_sn: int
    approval_request_docs_dtl_sn: int
    status: ApprovalReviewJobStatus
    status_url: str
    message: str


class ApprovalReviewJobError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class ApprovalReviewJobStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    docs_aprv_sn: int
    docs_sn: int
    approval_request_docs_dtl_sn: int
    before_docs_dtl_sn: int | None = None
    after_docs_dtl_sn: int | None = None
    before_data: Any | None = None
    after_data: Any | None = None
    status: ApprovalReviewJobStatus
    step: str | None = None
    progress: int
    message: str | None = None
    requested_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: ApprovalReviewResponse | None = None
    error: ApprovalReviewJobError | None = None
