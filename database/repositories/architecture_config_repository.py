from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from database.queries.architecture_config_query import (
    FIND_ARCHITECTURE_CONFIG_BY_PROJECT_SN,
)


class ArchitectureConfigRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_by_project_sn(self, project_sn: int) -> Any | None:
        rows = self.session.execute(
            text(FIND_ARCHITECTURE_CONFIG_BY_PROJECT_SN),
            {"project_sn": project_sn},
        ).mappings().all()
        configs = [dict(row) for row in rows]
        if not configs:
            return None
        return {"project_sn": project_sn, "networks": configs}
