FIND_DOCS_BY_CODE = """
SELECT
    code AS docs_cd,
    code_nm AS docs_nm,
    rmrk_cn
FROM tbl_code
WHERE code = :docs_cd
"""

FIND_ALL_DOCS = """
SELECT
    code AS docs_cd,
    code_nm AS docs_nm,
    rmrk_cn
FROM tbl_code
WHERE code LIKE 'DOC_%'
ORDER BY code
"""

FIND_PROJECT_DOCS_BY_CODE = """
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
