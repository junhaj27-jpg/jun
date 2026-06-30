from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from config.constants import DOCS_CODES, normalize_docs_cd
from schemas.common.common_schema import DocsCode, UpdateYn
from schemas.common.file_schema import FileSn


class GenerationRequest(BaseModel):
    """산출물 생성 워크플로우를 시작하기 위한 요청입니다."""

    model_config = ConfigDict(extra="forbid")

    project_sn: int
    docs_cd: DocsCode
    udt_yn: UpdateYn
    request_docs_detail_sn: int | None = Field(default=None, gt=0)
    docs_sn: int | None = Field(default=None, gt=0)
    file_list: list[FileSn] = Field(default_factory=list)
    image_list: list[str] = Field(default_factory=list)
    etc: dict[str, Any] = Field(default_factory=dict)

    @field_validator("docs_cd", mode="before")
    @classmethod
    def validate_docs_cd(cls, value: Any) -> str:
        normalized = normalize_docs_cd(value)
        if normalized not in DOCS_CODES:
            raise ValueError(f"지원하지 않는 docs_cd입니다: {value}")
        return normalized
