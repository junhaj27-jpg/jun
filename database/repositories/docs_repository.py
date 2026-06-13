from typing import Any

from sqlalchemy.orm import Session

from schemas.common.common_schema import DocsCode


class DocsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_docs_by_code(self, docs_cd: DocsCode) -> Any | None:
        raise NotImplementedError

    def find_all_docs(self) -> list[Any]:
        raise NotImplementedError
