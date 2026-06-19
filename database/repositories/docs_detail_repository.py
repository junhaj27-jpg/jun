from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from config.constants import (
    DOCS_CODE_DB_MAP,
    DOCS_PROGRESS_DB_MAP,
    FILE_CODE_REQUIREMENT_JSON,
)
from database.repositories.file_repository import FileRepository
from database.queries.docs_detail_query import (
    FIND_ACTIVE_DOC,
    FIND_ACTIVE_SRS,
    FIND_CURRENT_DOCS,
    INSERT_DOCS,
    INSERT_DOCS_DETAIL,
    UPDATE_DOCS_STATUS,
)
from schemas.common.common_schema import DocsCode


class DocsDetailRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_active_srs(self, project_sn: int) -> Any | None:
        return FileRepository(self.session).find_latest_file_by_project_and_code(
            project_sn, FILE_CODE_REQUIREMENT_JSON
        )

    def find_active_doc(self, project_sn: int, docs_cd: DocsCode) -> Any | None:
        row = self.session.execute(
            text(FIND_ACTIVE_SRS if str(docs_cd) == "SRS" else FIND_ACTIVE_DOC),
            {"project_sn": project_sn, "docs_cd": _to_db_docs_cd(docs_cd)},
        ).mappings().first()
        return _normalize_docs_row(row)

    def update_docs_status_generating(
        self,
        project_sn: int,
        docs_cd: DocsCode,
    ) -> None:
        self._update_docs_status(
            project_sn=project_sn,
            docs_cd=docs_cd,
            status="GENERATING",
            mdfcn_cn="산출물 생성 중",
        )

    def ensure_docs_status_generating(
        self,
        project_sn: int,
        docs_cd: DocsCode,
    ) -> int | None:
        return self._upsert_docs_status(
            project_sn=project_sn,
            docs_cd=docs_cd,
            status="GENERATING",
            mdfcn_cn="산출물 생성 중",
        )

    def update_docs_status_done(self, project_sn: int, docs_cd: DocsCode) -> None:
        self._update_docs_status(
            project_sn=project_sn,
            docs_cd=docs_cd,
            status="DONE",
            mdfcn_cn="산출물 생성 완료",
        )

    def update_docs_status_failed(
        self,
        project_sn: int,
        docs_cd: DocsCode,
        error_message: str,
    ) -> None:
        self._update_docs_status(
            project_sn=project_sn,
            docs_cd=docs_cd,
            status="FAILED",
            mdfcn_cn=(error_message or "산출물 생성 실패")[:100],
        )

    def deactivate_active_doc(self, project_sn: int, docs_cd: DocsCode) -> None:
        return None

    def insert_docs_detail(
        self,
        *,
        project_sn: int,
        docs_cd: DocsCode,
        docs_path: str | None = None,
        file_sn: int | None = None,
        storage_file_path: str | None = None,
        docs_dtl_cn: bytes | None = None,
        use_yn: str = "Y",  # backward-compatible; tbl_docs_detail uses del_yn.
        status: str = "DONE",
        user_sn: int = 1,
        docs_ver: str | None = None,
    ) -> Any:
        docs_sn = self._find_docs_sn(
            project_sn=project_sn,
            docs_cd=docs_cd,
            docs_ver=docs_ver,
        )
        result = self.session.execute(
            text(INSERT_DOCS_DETAIL),
            {
                "docs_sn": docs_sn,
                "docs_dtl_cn": docs_dtl_cn,
                "docs_path": docs_path or storage_file_path or "",
                "user_sn": user_sn,
            },
        )
        return {"docs_sn": docs_sn, "docs_dtl_sn": int(result.lastrowid)}

    def _update_docs_status(
        self,
        *,
        project_sn: int,
        docs_cd: DocsCode,
        status: str,
        mdfcn_cn: str | None,
        user_sn: int = 1,
    ) -> None:
        result = self.session.execute(
            text(UPDATE_DOCS_STATUS),
            {
                "project_sn": project_sn,
                "docs_cd": _to_db_docs_cd(docs_cd),
                "docs_prgrs_stts_cd": _to_db_status(status),
                "mdfcn_cn": mdfcn_cn,
                "user_sn": user_sn,
            },
        )
        if result.rowcount == 0:
            raise LookupError(
                f"tbl_docs row not found: project_sn={project_sn}, docs_cd={docs_cd}"
            )

    def _upsert_docs_status(
        self,
        *,
        project_sn: int,
        docs_cd: DocsCode,
        status: str,
        mdfcn_cn: str | None,
        user_sn: int = 1,
    ) -> int | None:
        result = self.session.execute(
            text(UPDATE_DOCS_STATUS),
            {
                "project_sn": project_sn,
                "docs_cd": _to_db_docs_cd(docs_cd),
                "docs_prgrs_stts_cd": _to_db_status(status),
                "mdfcn_cn": mdfcn_cn,
                "user_sn": user_sn,
            },
        )
        if result.rowcount != 0:
            return None
        return self._insert_docs(
            project_sn=project_sn,
            docs_cd=docs_cd,
            status=status,
            mdfcn_cn=mdfcn_cn,
            user_sn=user_sn,
        )

    def _find_docs_sn(
        self,
        *,
        project_sn: int,
        docs_cd: DocsCode,
        docs_ver: str | None = None,
    ) -> int:
        current = self.session.execute(
            text(FIND_CURRENT_DOCS),
            {"project_sn": project_sn, "docs_cd": _to_db_docs_cd(docs_cd)},
        ).mappings().first()
        if current is not None:
            return int(current["docs_sn"])
        return self._insert_docs(
            project_sn=project_sn,
            docs_cd=docs_cd,
            status="DONE",
            mdfcn_cn="산출물 생성 완료",
            docs_ver=docs_ver,
        )

    def _insert_docs(
        self,
        *,
        project_sn: int,
        docs_cd: DocsCode,
        status: str,
        mdfcn_cn: str | None,
        user_sn: int = 1,
        docs_ver: str | None = None,
    ) -> int:
        result = self.session.execute(
            text(INSERT_DOCS),
            {
                "project_sn": project_sn,
                "docs_cd": _to_db_docs_cd(docs_cd),
                "docs_ver": _normalize_docs_ver(docs_ver),
                "docs_prgrs_stts_cd": _to_db_status(status),
                "mdfcn_cn": mdfcn_cn,
                "user_sn": user_sn,
            },
        )
        return int(result.lastrowid)


def _to_db_docs_cd(docs_cd: DocsCode | str) -> str:
    return DOCS_CODE_DB_MAP.get(str(docs_cd), str(docs_cd))


def _to_db_status(status: str) -> str:
    return DOCS_PROGRESS_DB_MAP.get(status, status)


def _normalize_docs_ver(docs_ver: str | None) -> str:
    value = str(docs_ver or "").strip()
    return value or "v1.0"


def _normalize_docs_row(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    data.setdefault("project_sn", data.get("prj_sn"))
    data.setdefault("docs_detail_sn", data.get("docs_dtl_sn"))
    data.setdefault("file_path", data.get("docs_path"))
    return data
