from datetime import datetime

from sqlalchemy import LargeBinary, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class DocsDetail(Base):
    """tbl_docs_detail ORM 모델입니다."""

    __tablename__ = "tbl_docs_detail"

    docs_dtl_sn: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    docs_sn: Mapped[int] = mapped_column(Integer, nullable=False)
    docs_dtl_cn: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    docs_path: Mapped[str] = mapped_column(String(300), nullable=False)
    del_yn: Mapped[str] = mapped_column(String(1), nullable=False, default="N")
    crt_dt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    creatr_sn: Mapped[int] = mapped_column(Integer, nullable=False)

    @property
    def docs_detail_sn(self) -> int:
        return self.docs_dtl_sn
