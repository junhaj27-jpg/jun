FIND_ARCHITECTURE_CONFIG_BY_PROJECT_SN = """
SELECT
    prj_net_sn,
    prj_sn,
    prj_net_nm,
    prj_net_prps,
    mid_stack,
    fwl_settings,
    auth_method,
    expected_smtn,
    cloud_yn,
    hard_spec,
    rmrk,
    crt_dt,
    creatr_sn,
    mdfcn_dt,
    mdfr_sn
FROM tbl_project_net
WHERE prj_sn = :project_sn
ORDER BY prj_net_sn
"""
