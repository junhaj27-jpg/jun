from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from config.settings import get_settings


def create_database_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().resolved_database_url
    return create_engine(url, pool_pre_ping=True)


engine = create_database_engine()
