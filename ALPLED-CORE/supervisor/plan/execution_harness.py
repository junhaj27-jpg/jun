# 산출물별 Agent 실행 순서를 정의합니다.

EXECUTION_HARNESS: dict[tuple[str, str], list[str]] = {
    ("SRS", "N"): [
        "document_merge_agent",
        "requirement_generation_agent",
        "validation_agent",
    ],
    ("SRS", "Y"): ["document_merge_agent", "validation_agent"],
    ("INTERFACE", "N"): [
        "document_merge_agent",
        "image_analysis_agent",
        "validation_agent",
    ],
    ("INTERFACE", "Y"): [
        "document_merge_agent",
        "image_analysis_agent",
        "validation_agent",
    ],
    ("TS", "N"): [
        "document_merge_agent",
        "test_scenario_generation_agent",
        "validation_agent",
    ],
    ("TS", "Y"): [
        "document_merge_agent",
        "test_scenario_generation_agent",
        "validation_agent",
    ],
    ("ARCH", "N"): [
        "document_merge_agent",
        "architecture_analysis_agent",
        "mermaid_generation_agent",
        "validation_agent",
    ],
    ("ARCH", "Y"): [
        "document_merge_agent",
        "architecture_analysis_agent",
        "mermaid_generation_agent",
        "validation_agent",
    ],
    ("ERD", "N"): [
        "document_merge_agent",
        "data_structure_design_agent",
        "mermaid_generation_agent",
        "validation_agent",
    ],
    ("ERD", "Y"): [
        "document_merge_agent",
        "data_structure_design_agent",
        "mermaid_generation_agent",
        "validation_agent",
    ],
    ("DB", "N"): [
        "document_merge_agent",
        "data_structure_design_agent",
        "validation_agent",
    ],
    ("DB", "Y"): [
        "document_merge_agent",
        "data_structure_design_agent",
        "validation_agent",
    ],
}


def get_execution_agents(docs_cd: str, udt_yn: str) -> list[str]:
    try:
        return list(EXECUTION_HARNESS[(docs_cd, udt_yn)])
    except KeyError as exc:
        raise ValueError(f"지원하지 않는 실행 계획입니다: docs_cd={docs_cd}, udt_yn={udt_yn}") from exc
