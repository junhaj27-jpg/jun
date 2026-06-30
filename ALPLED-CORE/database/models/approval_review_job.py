from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class ApprovalReviewJob(Base):
    """산출물 승인 전 정합성 검증 작업을 관리합니다."""

    __tablename__ = "tbl_approval_review_job"
    __table_args__ = (
        UniqueConstraint("job_id", name="uk_approval_review_job_id"),
        UniqueConstraint("active_key", name="uk_approval_review_job_active_key"),
    )

    job_sn: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(36), nullable=False)
    docs_aprv_sn: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    docs_sn: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    approval_request_docs_dtl_sn: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True
    )
    before_docs_dtl_sn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    after_docs_dtl_sn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    before_data_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    after_data_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    job_stts_cd: Mapped[str] = mapped_column(
        String(30), nullable=False, default="QUEUED", index=True
    )
    job_step_cd: Mapped[str | None] = mapped_column(String(50), nullable=True)
    progress_rate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message_cn: Mapped[str | None] = mapped_column(String(500), nullable=True)

    request_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_cd: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)

    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    active_key: Mapped[str | None] = mapped_column(String(200), nullable=True)

    requested_dt: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )
    started_dt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_dt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    heartbeat_dt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_dt: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )
