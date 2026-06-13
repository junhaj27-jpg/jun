from typing import Any

from pydantic import BaseModel, ConfigDict

from schemas.common.common_schema import DocsCode, WorkflowStatus


class GenerationResponse(BaseModel):
    """산출물 생성 요청의 접수 및 처리 상태 응답입니다."""

    model_config = ConfigDict(extra="forbid")

    project_sn: int
    docs_cd: DocsCode
    status: WorkflowStatus
    message: str | None = None
    result: dict[str, Any] | None = None
