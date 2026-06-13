from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from schemas.common.common_schema import DocsCode, UpdateYn
from schemas.common.file_schema import FileSn


class GenerationRequest(BaseModel):
    """산출물 생성 워크플로우를 시작하기 위한 요청입니다."""

    model_config = ConfigDict(extra="forbid")

    project_sn: int
    docs_cd: DocsCode
    udt_yn: UpdateYn
    file_list: list[FileSn] = Field(default_factory=list)
    image_list: list[FileSn] = Field(default_factory=list)
    etc: dict[str, Any] = Field(default_factory=dict)
