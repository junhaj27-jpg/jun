from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Docs(Base):
    """tbl_docs ORM 모델입니다."""

    __tablename__ = "tbl_docs"

    docs_sn: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prj_sn: Mapped[int] = mapped_column(Integer, nullable=False)
    pssn_user_sn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    docs_cd: Mapped[str] = mapped_column(String(100), nullable=False)
    docs_ver: Mapped[str] = mapped_column(String(20), nullable=False, default="v1.0")
    docs_prgrs_stts_cd: Mapped[str] = mapped_column(
        String(100), nullable=False, default="PRGRS_PENDING"
    )
    mdfcn_cn: Mapped[str | None] = mapped_column(String(100), nullable=True)
    crt_dt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    creatr_sn: Mapped[int] = mapped_column(Integer, nullable=False)
    mdfcn_dt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    mdfr_sn: Mapped[int] = mapped_column(Integer, nullable=False)
