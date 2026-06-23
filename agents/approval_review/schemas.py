from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


ReviewStatus = Literal["ok", "issues_found", "failed", "skipped"]


class ApprovalReviewRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    docs_sn: int = Field(
        gt=0,
        validation_alias=AliasChoices("docs_sn", "docsSn"),
    )
    approval_request_docs_dtl_sn: int = Field(
        gt=0,
        validation_alias=AliasChoices(
            "approval_request_docs_dtl_sn",
            "approvalRequestDocsDtlSn",
            "docs_dtl_sn",
            "docsDtlSn",
            "docs_detail_sn",
        ),
    )


class ApprovalReviewResponse(BaseModel):
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
