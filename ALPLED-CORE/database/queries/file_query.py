FIND_FILE_BY_SN = """
SELECT
    file_sn,
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
FROM tbl_file
WHERE file_sn = :file_sn
"""

FIND_FILES_BY_SN_LIST = """
SELECT
    file_sn,
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
FROM tbl_file
WHERE file_sn IN :file_sn_list
ORDER BY file_sn
"""

FIND_LATEST_FILE_BY_PROJECT_AND_CODE = """
SELECT
    file_sn,
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
FROM tbl_file
WHERE prj_sn = :project_sn
  AND file_cd = :file_cd
ORDER BY file_sn DESC
LIMIT 1
"""

INSERT_FILE = """
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
VALUES (
    :project_sn,
    :file_cd,
    :file_nm,
    :file_path,
    :file_size,
    :file_ext,
    NOW(),
    :user_sn,
    NOW(),
    :user_sn
)
"""
