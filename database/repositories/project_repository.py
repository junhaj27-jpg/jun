from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from database.queries.project_query import EXISTS_PROJECT, FIND_PROJECT_BY_SN


class ProjectRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_project_by_sn(self, project_sn: int) -> Any | None:
        row = self.session.execute(
            text(FIND_PROJECT_BY_SN), {"project_sn": project_sn}
        ).mappings().first()
        return dict(row) if row is not None else None

    def exists_project(self, project_sn: int) -> bool:
        row = self.session.execute(
            text(EXISTS_PROJECT), {"project_sn": project_sn}
        ).first()
        return row is not None
