from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class DocsDetail(Base):
    """tbl_docs_detail ORM placeholder입니다."""

    __tablename__ = "tbl_docs_detail"

    docs_detail_sn: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_sn: Mapped[int] = mapped_column(Integer, nullable=False)
    docs_cd: Mapped[str] = mapped_column(String(20), nullable=False)
    file_sn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    use_yn: Mapped[str] = mapped_column(String(1), default="Y")
    docs_prgrs_stts_cd: Mapped[str | None] = mapped_column(String(30), nullable=True)
    fail_rsn: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    crt_dt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    upd_dt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
