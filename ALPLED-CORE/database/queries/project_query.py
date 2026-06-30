FIND_PROJECT_BY_SN = """
SELECT
    prj_sn,
    prj_nm,
    del_yn,
    crt_dt,
    creatr_sn,
    mdfcn_dt,
    mdfr_sn
FROM tbl_project
WHERE prj_sn = :project_sn
  AND del_yn = 'N'
"""

EXISTS_PROJECT = """
SELECT 1
FROM tbl_project
WHERE prj_sn = :project_sn
  AND del_yn = 'N'
LIMIT 1
"""
