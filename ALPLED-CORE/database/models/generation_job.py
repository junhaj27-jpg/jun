from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, JSON, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from config.constants import GenerationJobStatus
from database.base import Base


class GenerationJob(Base):
    """tbl_generation_job ORM model."""

    __tablename__ = "tbl_generation_job"
    __table_args__ = (
        UniqueConstraint("job_id", name="uk_tbl_generation_job_job_id"),
        UniqueConstraint("active_key", name="uk_generation_job_active_key"),
        Index("idx_tbl_generation_job_stts_requested_dt", "job_stts_cd", "requested_dt"),
        Index("idx_tbl_generation_job_prj_docs_cd", "prj_sn", "docs_cd"),
        Index("idx_tbl_generation_job_docs_sn", "docs_sn"),
        Index("idx_tbl_generation_job_request_id", "request_id"),
    )

    job_sn: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(36), nullable=False)

    prj_sn: Mapped[int] = mapped_column(Integer, nullable=False)
    docs_cd: Mapped[str] = mapped_column(String(100), nullable=False)
    docs_sn: Mapped[int | None] = mapped_column(Integer, nullable=True)

    job_stts_cd: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default=GenerationJobStatus.PENDING.value,
        server_default=text("'PRGRS_PENDING'"),
    )
    progress_rate: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    request_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_cd: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)

    retry_cnt: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    max_retry_cnt: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    active_key: Mapped[str | None] = mapped_column(String(200), nullable=True)

    requested_dt: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.now,
        server_default=func.now(),
    )
    started_dt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_dt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    heartbeat_dt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_dt: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.now,
        server_default=func.now(),
        onupdate=func.now(),
    )

    @property
    def project_sn(self) -> int:
        return self.prj_sn
