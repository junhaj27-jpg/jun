from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from config.constants import FILE_CODE_GENERATED_DOC
from database.queries.file_query import (
    FIND_FILE_BY_SN,
    FIND_FILES_BY_SN_LIST,
    FIND_LATEST_FILE_BY_PROJECT_AND_CODE,
    INSERT_FILE,
)
from schemas.common.file_schema import FileSn


class FileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_file_by_sn(self, file_sn: FileSn) -> Any | None:
        row = self.session.execute(
            text(FIND_FILE_BY_SN), {"file_sn": file_sn}
        ).mappings().first()
        return _normalize_file_row(row)

    def find_files_by_sn_list(self, file_sn_list: list[FileSn]) -> list[Any]:
        if not file_sn_list:
            return []
        statement = text(FIND_FILES_BY_SN_LIST).bindparams(
            bindparam("file_sn_list", expanding=True)
        )
        rows = self.session.execute(
            statement, {"file_sn_list": list(file_sn_list)}
        ).mappings().all()
        return [_normalize_file_row(row) for row in rows]

    def find_latest_file_by_project_and_code(
        self, project_sn: int, file_cd: str
    ) -> Any | None:
        row = self.session.execute(
            text(FIND_LATEST_FILE_BY_PROJECT_AND_CODE),
            {"project_sn": project_sn, "file_cd": file_cd},
        ).mappings().first()
        return _normalize_file_row(row)

    def insert_file(
        self,
        *,
        project_sn: int,
        file_nm: str,
        file_path: str,
        file_size: int,
        file_ext: str | None = None,
        file_extn: str | None = None,
        file_cd: str = FILE_CODE_GENERATED_DOC,
        user_sn: int = 1,
    ) -> Any:
        result = self.session.execute(
            text(INSERT_FILE),
            {
                "project_sn": project_sn,
                "file_cd": file_cd,
                "file_nm": file_nm,
                "file_path": file_path,
                "file_size": file_size,
                "file_ext": (file_ext or file_extn or "").lstrip(".")[:4],
                "user_sn": user_sn,
            },
        )
        return {"file_sn": int(result.lastrowid)}


def _normalize_file_row(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    data.setdefault("project_sn", data.get("prj_sn"))
    data.setdefault("file_extn", data.get("file_ext"))
    return data
