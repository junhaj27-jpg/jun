from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Project(Base):
    """tbl_project ORM placeholder입니다."""

    __tablename__ = "tbl_project"

    project_sn: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_nm: Mapped[str | None] = mapped_column(String(255), nullable=True)
    crt_dt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
