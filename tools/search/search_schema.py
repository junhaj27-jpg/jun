from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


SearchTarget = Literal["RAG", "WEB", "BOTH", "NONE"]
SearchSource = Literal["RAG", "WEB"]


class SearchRequest(BaseModel):
    """Agent가 Search Tool에 전달하는 검색 요청입니다."""

    model_config = ConfigDict(extra="forbid")

    project_sn: int | None = None
    docs_cd: str | None = None
    agent_name: str | None = None
    search_intent: str | None = None
    query: str = Field(min_length=1)
    search_targets: SearchTarget = "RAG"
    filters: dict[str, Any] | None = None
    top_k: int = Field(default=5, ge=1, le=100)
    query_vector: list[float] | None = None
    collection: str | None = None

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("query는 비어 있을 수 없습니다.")
        return query


class SearchResult(BaseModel):
    """RAG/Web 검색 결과의 공통 형식입니다."""

    model_config = ConfigDict(extra="forbid")

    source_kind: SearchSource
    id: str | int
    title: str = ""
    content: str = ""
    url: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    citation: str = ""

    @property
    def source(self) -> SearchSource:
        """기존 테스트와 Agent 호환을 위한 별칭입니다."""

        return self.source_kind

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        data = super().model_dump(*args, **kwargs)
        data["source"] = data["source_kind"]
        return data
