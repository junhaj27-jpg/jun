from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class File(Base):
    """tbl_file ORM 모델입니다."""

    __tablename__ = "tbl_file"

    file_sn: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prj_sn: Mapped[int] = mapped_column(Integer, nullable=False)
    file_cd: Mapped[str] = mapped_column(String(100), nullable=False)
    file_nm: Mapped[str] = mapped_column(String(100), nullable=False)
    file_path: Mapped[str] = mapped_column(String(300), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    file_ext: Mapped[str] = mapped_column(String(4), nullable=False)
    crt_dt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    creatr_sn: Mapped[int] = mapped_column(Integer, nullable=False)
    mdfcn_dt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    mdfr_sn: Mapped[int] = mapped_column(Integer, nullable=False)

    @property
    def file_extn(self) -> str:
        return self.file_ext
