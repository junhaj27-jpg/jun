from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class ArchitectureConfig(Base):
    """아키텍처 설정으로 사용하는 tbl_project_net ORM 모델입니다."""

    __tablename__ = "tbl_project_net"

    prj_net_sn: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prj_sn: Mapped[int] = mapped_column(Integer, nullable=False)
    prj_net_nm: Mapped[str] = mapped_column(String(100), nullable=False)
    prj_net_prps: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    mid_stack: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    fwl_settings: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    auth_method: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    expected_smtn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cloud_yn: Mapped[str | None] = mapped_column(String(1), nullable=True)
    hard_spec: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    rmrk: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    crt_dt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    creatr_sn: Mapped[int] = mapped_column(Integer, nullable=False)
    mdfcn_dt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    mdfr_sn: Mapped[int] = mapped_column(Integer, nullable=False)

    @property
    def project_sn(self) -> int:
        return self.prj_sn
