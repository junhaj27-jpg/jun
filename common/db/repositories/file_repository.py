from pathlib import Path
from typing import Any

from common.db.connection import db_connection


def get_file_by_file_sn(prj_sn: int, file_sn: int) -> dict[str, Any]:
    rows = get_files_by_file_sns(prj_sn, [file_sn])
    if not rows:
        raise FileNotFoundError(f"파일을 찾지 못했습니다. prj_sn={prj_sn}, file_sn={file_sn}")
    return rows[0]


def get_files_by_file_sns(prj_sn: int, file_sns: list[int]) -> list[dict[str, Any]]:
    if not file_sns:
        return []

    placeholders = ", ".join(["%s"] * len(file_sns))
    sql = f"""
        SELECT
            file_sn,
            prj_sn,
            file_cd,
            file_nm,
            file_path,
            file_size,
            file_ext
        FROM tbl_file
        WHERE prj_sn = %s
          AND file_sn IN ({placeholders})
    """
    with db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, [prj_sn, *file_sns])
            rows = cursor.fetchall()

    found = {int(row["file_sn"]) for row in rows}
    missing = [file_sn for file_sn in file_sns if int(file_sn) not in found]
    if missing:
        raise FileNotFoundError(f"파일을 찾지 못했습니다. prj_sn={prj_sn}, file_sns={missing}")
    return rows


def insert_file_metadata(
    *,
    prj_sn: int,
    file_cd: str,
    file_path: str,
    login_user_sn: int,
) -> dict[str, int]:
    path = Path(file_path)
    sql = """
        INSERT INTO tbl_file (
            prj_sn,
            file_cd,
            file_nm,
            file_path,
            file_size,
            file_ext,
            crt_dt,
            creatr_sn,
            mdfcn_dt,
            mdfr_sn
        )
        VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s, NOW(), %s)
    """
    with db_connection() as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    sql,
                    (
                        prj_sn,
                        file_cd,
                        path.name,
                        str(path),
                        path.stat().st_size if path.exists() else 0,
                        path.suffix.lstrip(".").lower()[:4],
                        login_user_sn,
                        login_user_sn,
                    ),
                )
                file_sn = cursor.lastrowid
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {"file_sn": int(file_sn)}
