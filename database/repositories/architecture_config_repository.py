from typing import Any

from sqlalchemy.orm import Session


class ArchitectureConfigRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_by_project_sn(self, project_sn: int) -> Any | None:
        raise NotImplementedError
