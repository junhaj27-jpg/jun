from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Project(Base):
    """tbl_project ORM 모델입니다."""

    __tablename__ = "tbl_project"

    prj_sn: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prj_nm: Mapped[str] = mapped_column(String(200), nullable=False)
    del_yn: Mapped[str] = mapped_column(String(1), nullable=False, default="N")
    crt_dt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    creatr_sn: Mapped[int] = mapped_column(Integer, nullable=False)
    mdfcn_dt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    mdfr_sn: Mapped[int] = mapped_column(Integer, nullable=False)

    @property
    def project_sn(self) -> int:
        return self.prj_sn

    @property
    def project_nm(self) -> str:
        return self.prj_nm
