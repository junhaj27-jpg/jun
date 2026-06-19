from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class CommonRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def fetch_one(self, query: str, params: dict[str, Any] | None = None) -> Any | None:
        row = self.session.execute(text(query), params or {}).mappings().first()
        return dict(row) if row is not None else None

    def fetch_all(self, query: str, params: dict[str, Any] | None = None) -> list[Any]:
        rows = self.session.execute(text(query), params or {}).mappings().all()
        return [dict(row) for row in rows]

    def execute(self, query: str, params: dict[str, Any] | None = None) -> Any:
        return self.session.execute(text(query), params or {})
