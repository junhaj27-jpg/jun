from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class File(Base):
    """tbl_file ORM placeholder입니다."""

    __tablename__ = "tbl_file"

    file_sn: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_nm: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_extn: Mapped[str | None] = mapped_column(String(30), nullable=True)
    crt_dt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
