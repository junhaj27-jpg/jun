from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from config.constants import FILE_CODE_REQUIREMENT_JSON
from config.settings import Settings, get_settings


class ApprovalReviewRepository:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    def get_docs(self, docs_sn: int) -> dict[str, Any] | None:
        row = self.session.execute(
            text(
                """
                SELECT docs_sn, prj_sn, docs_cd
                FROM tbl_docs
                WHERE docs_sn = :docs_sn
                """
            ),
            {"docs_sn": docs_sn},
        ).mappings().first()
        return dict(row) if row is not None else None

    def get_first_docs_detail(self, docs_sn: int) -> dict[str, Any] | None:
        row = self.session.execute(
            text(
                """
                SELECT docs_dtl_sn, docs_sn, docs_dtl_cn, docs_path,
                       del_yn, crt_dt, creatr_sn
                FROM tbl_docs_detail
                WHERE docs_sn = :docs_sn
                  AND del_yn = 'N'
                ORDER BY crt_dt ASC, docs_dtl_sn ASC
                LIMIT 1
                """
            ),
            {"docs_sn": docs_sn},
        ).mappings().first()
        return dict(row) if row is not None else None

    def get_docs_detail(
        self, docs_sn: int, docs_dtl_sn: int
    ) -> dict[str, Any] | None:
        row = self.session.execute(
            text(
                """
                SELECT docs_dtl_sn, docs_sn, docs_dtl_cn, docs_path,
                       del_yn, crt_dt, creatr_sn
                FROM tbl_docs_detail
                WHERE docs_sn = :docs_sn
                  AND docs_dtl_sn = :docs_dtl_sn
                  AND del_yn = 'N'
                """
            ),
            {"docs_sn": docs_sn, "docs_dtl_sn": docs_dtl_sn},
        ).mappings().first()
        return dict(row) if row is not None else None

    def get_latest_requirement_json(
        self, prj_sn: int
    ) -> dict[str, Any] | None:
        statement = text(
            """
            SELECT file_sn, prj_sn, file_cd, file_nm,
                   file_path AS docs_path, file_ext, crt_dt
            FROM tbl_file
            WHERE prj_sn = :prj_sn
              AND file_cd = :file_cd
            ORDER BY file_sn DESC
            LIMIT 1
            """
        )
        row = self.session.execute(
            statement,
            {
                "prj_sn": prj_sn,
                "file_cd": FILE_CODE_REQUIREMENT_JSON,
            },
        ).mappings().first()
        if row is None:
            return None
        result = dict(row)
        result["docs_dtl_cn"] = None
        return result
