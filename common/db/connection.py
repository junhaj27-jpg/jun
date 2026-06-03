import os
from contextlib import contextmanager
from typing import Iterator

from dotenv import load_dotenv

load_dotenv()


def get_connection():
    try:
        import pymysql
    except ImportError as exc:
        raise RuntimeError("PyMySQL이 필요합니다. requirements.txt 설치 후 다시 실행하세요.") from exc

    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        database=os.getenv("DB_NAME", "arkive"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", "password"),
        charset=os.getenv("DB_CHARSET", "utf8mb4"),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


@contextmanager
def db_connection() -> Iterator:
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
