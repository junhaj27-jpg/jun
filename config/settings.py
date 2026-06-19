from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경변수 기반 애플리케이션 설정입니다."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # App
    app_name: str = "ALPLED-CORE"
    app_env: str = "local"
    app_debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    db_driver: str = "mysql+pymysql"
    db_host: str | None = None
    db_port: int = 3306
    db_name: str | None = None
    db_user: str | None = None
    db_password: str | None = None

    # S3
    s3_endpoint: str | None = None
    s3_bucket: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str = "ap-northeast-2"

    # Qdrant
    qdrant_url: str | None = None
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_api_key: str | None = None
    alpled_reference_collection: str = Field(
        default="ALPLED_reference",
        validation_alias="ALPLED_REFERENCE_COLLECTION",
    )
    embed_model_name: str = Field(
        default="BAAI/bge-m3",
        validation_alias=AliasChoices("EMBED_MODEL_NAME", "EMBEDDING_MODEL"),
    )

    # LLM
    llm_base_url: str = "http://localhost:8000/v1"
    llm_api_key: str | None = None
    llm_model_name: str = "Qwen/Qwen3-VL-8B-Instruct"
    llm_timeout: float = Field(default=300, gt=0)
    llm_temperature: float = Field(default=0.2, ge=0)
    llm_max_tokens: int = Field(default=8192, gt=0)

    # Storage
    local_storage_root: Path = Path("./storage")
    input_dir: Path = Path("./storage/input")
    output_dir: Path = Path("./storage/output")
    temp_dir: Path = Path("./storage/temp")
    extract_image_dir: Path = Path("./storage/extracted_images")
    mermaid_dir: Path = Path("./storage/mermaid")
    mermaid_cli_path: str = "mmdc"
    mermaid_render_width: int = Field(default=2600, gt=0)
    mermaid_render_height: int = Field(default=1800, gt=0)
    mermaid_render_scale: int = Field(default=3, gt=0)

    # Log
    log_level: str = "INFO"
    log_file: Path = Path("./logs/alpled.log")

    # Supervisor
    max_round: int = Field(default=3, ge=1)

    @property
    def resolved_database_url(self) -> str:
        if self.db_host and self.db_name and self.db_user is not None:
            user = quote_plus(self.db_user)
            password = quote_plus(self.db_password or "")
            return (
                f"{self.db_driver}://{user}:{password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        return "sqlite:///./alpled.db"

    @property
    def resolved_qdrant_url(self) -> str:
        if self.qdrant_url:
            return self.qdrant_url
        return f"http://{self.qdrant_host}:{self.qdrant_port}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
