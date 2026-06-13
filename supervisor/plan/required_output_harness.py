# Agent별 필수 출력 키를 정의합니다.

AGENT_REQUIRED_OUTPUTS: dict[str, list[str]] = {
    "requirement_generation_agent": ["final_requirement_json_list"],
    "image_analysis_agent": ["interface_image_analysis_json_list"],
    "test_scenario_generation_agent": ["integrated_test_scenario_json"],
    "architecture_analysis_agent": [
        "architecture_structure_json",
        "architecture_document_json",
    ],
    "mermaid_generation_agent": ["mermaid_code", "mermaid_image_path"],
    "validation_agent": ["validation_result"],
}


def get_required_output_keys(agent_name: str, docs_cd: str, udt_yn: str) -> list[str]:
    if agent_name == "document_merge_agent":
        if udt_yn == "Y":
            if docs_cd in {"ERD", "DB", "ARCH"}:
                return ["existing_output_raw_json", "meeting_change_items"]
            return ["integrated_artifact_json_list"]
        required = ["integrated_requirement_json_list"]
        if docs_cd == "DB":
            required.append("reference_erd_json_list")
        elif docs_cd == "TS":
            required.append("reference_interface_json_list")
        return required

    if agent_name == "data_structure_design_agent":
        if docs_cd == "ERD":
            return ["erd_entity_json", "erd_mermaid_json"]
        if docs_cd == "DB":
            return ["db_design_json"]

    return list(AGENT_REQUIRED_OUTPUTS.get(agent_name, []))
