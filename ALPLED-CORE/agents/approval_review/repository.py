from __future__ import annotations

import hashlib
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

    def get_approval_request(self, docs_aprv_sn: int) -> dict[str, Any] | None:
        row = self.session.execute(
            text(
                """
                SELECT a.docs_aprv_sn,
                       a.docs_dtl_sn AS approval_request_docs_dtl_sn,
                       a.aprv_stts_cd,
                       a.dmnd_cn,
                       dd.docs_sn,
                       d.prj_sn,
                       d.docs_cd
                FROM tbl_docs_approve a
                JOIN tbl_docs_detail dd
                  ON dd.docs_dtl_sn = a.docs_dtl_sn
                 AND dd.del_yn = 'N'
                JOIN tbl_docs d
                  ON d.docs_sn = dd.docs_sn
                WHERE a.docs_aprv_sn = :docs_aprv_sn
                """
            ),
            {"docs_aprv_sn": docs_aprv_sn},
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

    def get_previous_docs_detail(
        self,
        docs_sn: int,
        after_docs_dtl_sn: int,
    ) -> dict[str, Any] | None:
        row = self.session.execute(
            text(
                """
                SELECT docs_dtl_sn, docs_sn, docs_dtl_cn, docs_path,
                       del_yn, crt_dt, creatr_sn
                FROM tbl_docs_detail
                WHERE docs_sn = :docs_sn
                  AND docs_dtl_sn < :after_docs_dtl_sn
                  AND del_yn = 'N'
                ORDER BY docs_dtl_sn DESC
                LIMIT 1
                """
            ),
            {
                "docs_sn": docs_sn,
                "after_docs_dtl_sn": after_docs_dtl_sn,
            },
        ).mappings().first()
        return dict(row) if row is not None else None

    def get_review_docs_detail_pair(
        self,
        docs_sn: int,
        approval_request_docs_dtl_sn: int | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """같은 docs_sn의 최초 상세와 최신 실질 변경 상세를 반환합니다.

        승인 요청 과정에서 최신 docs_detail을 그대로 복제한 행이 만들어질 수 있으므로
        마지막 행이 직전 행과 같은 파일/내용이면 비교 대상 after에서 제외합니다.
        """

        rows = self.session.execute(
            text(
                """
                SELECT docs_dtl_sn, docs_sn, docs_dtl_cn, docs_path,
                       del_yn, crt_dt, creatr_sn
                FROM tbl_docs_detail
                WHERE docs_sn = :docs_sn
                  AND del_yn = 'N'
                  AND (
                        :approval_request_docs_dtl_sn IS NULL
                        OR docs_dtl_sn <= :approval_request_docs_dtl_sn
                      )
                ORDER BY docs_dtl_sn ASC
                """
            ),
            {
                "docs_sn": docs_sn,
                "approval_request_docs_dtl_sn": approval_request_docs_dtl_sn,
            },
        ).mappings().all()
        details = [dict(row) for row in rows]
        if not details:
            return None, None
        before = details[0]
        if len(details) == 1:
            return before, before

        after = details[-1]
        while len(details) >= 2 and _same_docs_detail_payload(details[-1], details[-2]):
            details.pop()
            after = details[-1]
        return before, after

    def get_baseline_docs_detail(
        self,
        docs_sn: int,
        after_docs_dtl_sn: int,
    ) -> dict[str, Any] | None:
        approved = self.session.execute(
            text(
                """
                SELECT dd.docs_dtl_sn, dd.docs_sn, dd.docs_dtl_cn, dd.docs_path,
                       dd.del_yn, dd.crt_dt, dd.creatr_sn
                FROM tbl_docs_detail dd
                JOIN tbl_docs_approve a
                  ON a.docs_dtl_sn = dd.docs_dtl_sn
                WHERE dd.docs_sn = :docs_sn
                  AND dd.docs_dtl_sn < :after_docs_dtl_sn
                  AND dd.del_yn = 'N'
                  AND a.aprv_stts_cd = 'APRV_COM'
                ORDER BY a.mdfcn_dt DESC, dd.docs_dtl_sn DESC
                LIMIT 1
                """
            ),
            {
                "docs_sn": docs_sn,
                "after_docs_dtl_sn": after_docs_dtl_sn,
            },
        ).mappings().first()
        if approved is not None:
            return dict(approved)

        first = self.session.execute(
            text(
                """
                SELECT docs_dtl_sn, docs_sn, docs_dtl_cn, docs_path,
                       del_yn, crt_dt, creatr_sn
                FROM tbl_docs_detail
                WHERE docs_sn = :docs_sn
                  AND docs_dtl_sn < :after_docs_dtl_sn
                  AND del_yn = 'N'
                ORDER BY crt_dt ASC, docs_dtl_sn ASC
                LIMIT 1
                """
            ),
            {
                "docs_sn": docs_sn,
                "after_docs_dtl_sn": after_docs_dtl_sn,
            },
        ).mappings().first()
        return dict(first) if first is not None else None

    def get_latest_docs_detail(self, docs_sn: int) -> dict[str, Any] | None:
        row = self.session.execute(
            text(
                """
                SELECT docs_dtl_sn, docs_sn, docs_dtl_cn, docs_path,
                       del_yn, crt_dt, creatr_sn
                FROM tbl_docs_detail
                WHERE docs_sn = :docs_sn
                  AND del_yn = 'N'
                ORDER BY docs_dtl_sn DESC
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


def _same_docs_detail_payload(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        _normalize_docs_path(left.get("docs_path")) == _normalize_docs_path(right.get("docs_path"))
        and _blob_digest(left.get("docs_dtl_cn")) == _blob_digest(right.get("docs_dtl_cn"))
    )


def _normalize_docs_path(value: Any) -> str:
    return str(value or "").strip()


def _blob_digest(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytes):
        data = value
    else:
        data = str(value).encode("utf-8", errors="replace")
    return hashlib.sha256(data).hexdigest()
