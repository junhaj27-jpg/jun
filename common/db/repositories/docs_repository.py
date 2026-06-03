from typing import Any

from common.db.connection import db_connection


def get_docs_detail_by_docs_sn(prj_sn: int, docs_sn: int) -> dict[str, Any]:
    sql = """
        SELECT
            d.docs_sn,
            d.prj_sn,
            d.docs_cd,
            d.docs_ver,
            dd.docs_dtl_sn,
            dd.docs_path
        FROM tbl_docs d
        JOIN tbl_docs_detail dd
          ON d.docs_sn = dd.docs_sn
        WHERE d.docs_sn = %s
          AND d.prj_sn = %s
          AND dd.del_yn = 'N'
        ORDER BY dd.docs_dtl_sn DESC
        LIMIT 1
    """
    with db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (docs_sn, prj_sn))
            row = cursor.fetchone()
    if not row:
        raise FileNotFoundError(f"산출물 상세를 찾지 못했습니다. prj_sn={prj_sn}, docs_sn={docs_sn}")
    return row


def insert_docs_with_detail(
    prj_sn: int,
    docs_cd: str,
    docs_ver: str,
    mdfcn_cn: str,
    docs_path: str,
    login_user_sn: int,
    pssn_user_sn: int | None = None,
) -> dict[str, int]:
    docs_sql = """
        INSERT INTO tbl_docs (
            prj_sn,
            pssn_user_sn,
            docs_cd,
            docs_ver,
            mdfcn_cn,
            crt_dt,
            creatr_sn,
            mdfcn_dt,
            mdfr_sn
        )
        VALUES (%s, %s, %s, %s, %s, NOW(), %s, NOW(), %s)
    """
    detail_sql = """
        INSERT INTO tbl_docs_detail (
            docs_sn,
            docs_path,
            del_yn,
            crt_dt,
            creatr_sn
        )
        VALUES (%s, %s, 'N', NOW(), %s)
    """
    with db_connection() as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    docs_sql,
                    (
                        prj_sn,
                        pssn_user_sn if pssn_user_sn is not None else login_user_sn,
                        docs_cd,
                        docs_ver,
                        mdfcn_cn,
                        login_user_sn,
                        login_user_sn,
                    ),
                )
                docs_sn = cursor.lastrowid
                cursor.execute(detail_sql, (docs_sn, docs_path, login_user_sn))
                docs_dtl_sn = cursor.lastrowid
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {"docs_sn": int(docs_sn), "docs_dtl_sn": int(docs_dtl_sn)}
