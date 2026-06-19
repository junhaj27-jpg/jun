FIND_ACTIVE_DOC = """
SELECT
    d.docs_sn,
    d.prj_sn,
    d.docs_cd,
    d.docs_ver,
    d.docs_prgrs_stts_cd,
    d.mdfcn_cn,
    dd.docs_dtl_sn,
    dd.docs_path,
    dd.del_yn
FROM tbl_docs d
JOIN tbl_docs_detail dd
  ON dd.docs_sn = d.docs_sn
WHERE d.prj_sn = :project_sn
  AND d.docs_cd = :docs_cd
  AND dd.del_yn = 'N'
ORDER BY dd.docs_dtl_sn DESC
LIMIT 1
"""

FIND_ACTIVE_SRS = FIND_ACTIVE_DOC

FIND_CURRENT_DOCS = """
SELECT
    docs_sn,
    prj_sn,
    docs_cd,
    docs_ver,
    docs_prgrs_stts_cd,
    mdfcn_cn
FROM tbl_docs
WHERE prj_sn = :project_sn
  AND docs_cd = :docs_cd
ORDER BY docs_sn DESC
LIMIT 1
"""

INSERT_DOCS = """
INSERT INTO tbl_docs (
    prj_sn,
    pssn_user_sn,
    docs_cd,
    docs_ver,
    docs_prgrs_stts_cd,
    mdfcn_cn,
    crt_dt,
    creatr_sn,
    mdfcn_dt,
    mdfr_sn
)
VALUES (
    :project_sn,
    NULL,
    :docs_cd,
    :docs_ver,
    :docs_prgrs_stts_cd,
    :mdfcn_cn,
    NOW(),
    :user_sn,
    NOW(),
    :user_sn
)
"""

UPDATE_DOCS_STATUS = """
UPDATE tbl_docs
SET docs_prgrs_stts_cd = :docs_prgrs_stts_cd,
    mdfcn_cn = :mdfcn_cn,
    mdfcn_dt = NOW(),
    mdfr_sn = :user_sn
WHERE prj_sn = :project_sn
  AND docs_cd = :docs_cd
ORDER BY docs_sn DESC
LIMIT 1
"""

INSERT_DOCS_DETAIL = """
INSERT INTO tbl_docs_detail (
    docs_sn,
    docs_dtl_cn,
    docs_path,
    del_yn,
    crt_dt,
    creatr_sn
)
VALUES (
    :docs_sn,
    :docs_dtl_cn,
    :docs_path,
    'N',
    NOW(),
    :user_sn
)
"""
