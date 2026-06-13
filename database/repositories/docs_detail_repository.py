from typing import Any

from sqlalchemy.orm import Session

from schemas.common.common_schema import DocsCode


class DocsDetailRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_active_srs(self, project_sn: int) -> Any | None:
        raise NotImplementedError

    def find_active_doc(self, project_sn: int, docs_cd: DocsCode) -> Any | None:
        raise NotImplementedError

    def update_docs_status_generating(
        self,
        project_sn: int,
        docs_cd: DocsCode,
    ) -> None:
        raise NotImplementedError

    def update_docs_status_done(self, project_sn: int, docs_cd: DocsCode) -> None:
        raise NotImplementedError

    def update_docs_status_failed(
        self,
        project_sn: int,
        docs_cd: DocsCode,
        error_message: str,
    ) -> None:
        raise NotImplementedError

    def deactivate_active_doc(self, project_sn: int, docs_cd: DocsCode) -> None:
        raise NotImplementedError

    def insert_docs_detail(
        self,
        *,
        project_sn: int,
        docs_cd: DocsCode,
        file_sn: int,
        use_yn: str = "Y",
        status: str = "DONE",
    ) -> Any:
        raise NotImplementedError
