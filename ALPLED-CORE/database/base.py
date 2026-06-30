from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """모든 ORM 모델이 상속하는 SQLAlchemy 선언형 Base입니다."""
