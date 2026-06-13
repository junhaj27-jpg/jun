from typing import Any

from sqlalchemy.orm import Session


class ProjectRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_project_by_sn(self, project_sn: int) -> Any | None:
        raise NotImplementedError

    def exists_project(self, project_sn: int) -> bool:
        raise NotImplementedError
