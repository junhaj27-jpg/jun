from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from config.constants import DOCS_CODE_DB_MAP
from database.queries.docs_query import (
    FIND_ALL_DOCS,
    FIND_DOCS_BY_CODE,
    FIND_PROJECT_DOCS_BY_CODE,
)
from schemas.common.common_schema import DocsCode


class DocsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_docs_by_code(self, docs_cd: DocsCode) -> Any | None:
        row = self.session.execute(
            text(FIND_DOCS_BY_CODE),
            {"docs_cd": DOCS_CODE_DB_MAP.get(str(docs_cd), str(docs_cd))},
        ).mappings().first()
        return dict(row) if row is not None else None

    def find_project_docs_by_code(
        self,
        project_sn: int,
        docs_cd: DocsCode,
    ) -> Any | None:
        row = self.session.execute(
            text(FIND_PROJECT_DOCS_BY_CODE),
            {
                "project_sn": project_sn,
                "docs_cd": DOCS_CODE_DB_MAP.get(str(docs_cd), str(docs_cd)),
            },
        ).mappings().first()
        return dict(row) if row is not None else None

    def find_all_docs(self) -> list[Any]:
        rows = self.session.execute(text(FIND_ALL_DOCS)).mappings().all()
        return [dict(row) for row in rows]
