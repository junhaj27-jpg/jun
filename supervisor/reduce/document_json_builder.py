# 취합된 Agent 출력을 최종 산출물 JSON으로 생성합니다.

from typing import Any

from agents.requirement_generation.processors.requirement_refiner import (
    normalize_task3_output,
)
from supervisor.reduce.reduce_harness import get_empty_document_json
from workflow.state import WorkflowState


def build_final_document_json(state: WorkflowState) -> dict[str, Any]:
    docs_cd = state["docs_cd"]
    udt_yn = state.get("udt_yn")
    agent_outputs = state.get("agent_outputs", {})
    final_document_json = get_empty_document_json(docs_cd)

    if docs_cd == "SRS":
        if udt_yn == "Y":
            final_document_json["requirement_json_list"] = agent_outputs.get(
                "document_merge_agent", {}
            ).get("integrated_artifact_json_list", [])
        else:
            final_document_json["requirement_json_list"] = agent_outputs.get(
                "requirement_generation_agent", {}
            ).get("final_requirement_json_list", [])
        final_document_json["requirement_json_list"] = normalize_task3_output(
            final_document_json["requirement_json_list"]
        )
    elif docs_cd == "INTERFACE":
        image_output = agent_outputs.get("image_analysis_agent", {})
        final_document_json["interface_json_list"] = image_output.get("interface_image_analysis_json_list", [])
        final_document_json["ui_structure"] = image_output.get("ui_structure", [])
    elif docs_cd == "TS":
        final_document_json["integrated_test_scenario_json"] = agent_outputs.get(
            "test_scenario_generation_agent", {}
        ).get("integrated_test_scenario_json", {})
    elif docs_cd == "ERD":
        final_document_json["erd_entity_json"] = agent_outputs.get(
            "data_structure_design_agent", {}
        ).get("erd_entity_json", {})
        final_document_json["mermaid_image_path"] = agent_outputs.get(
            "mermaid_generation_agent", {}
        ).get("mermaid_image_path", "")
        final_document_json["mermaid_image_paths"] = agent_outputs.get(
            "mermaid_generation_agent", {}
        ).get("mermaid_image_paths", [])
        final_document_json["mermaid_groups"] = agent_outputs.get(
            "mermaid_generation_agent", {}
        ).get("mermaid_groups", [])
    elif docs_cd == "DB":
        final_document_json["db_design_json"] = agent_outputs.get(
            "data_structure_design_agent", {}
        ).get("db_design_json", {})
    elif docs_cd == "ARCH":
        arch_output = agent_outputs.get("architecture_analysis_agent", {})
        mermaid_output = agent_outputs.get("mermaid_generation_agent", {})

        final_document_json["architecture_structure_json"] = arch_output.get(
            "architecture_structure_json", {}
        )
        final_document_json["architecture_document_json"] = arch_output.get(
            "architecture_document_json", {}
        )
        final_document_json["mermaid_image_path"] = mermaid_output.get(
            "mermaid_image_path", ""
        )

    return final_document_json
