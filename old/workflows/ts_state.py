from typing import Any, TypedDict


class TestScenarioWorkflowState(TypedDict, total=False):
    requirement_json_path: str
    ui_paths: list[str]
    output_json_path: str
    output_docx_path: str
    max_retries: int

    requirement_doc: dict[str, Any]
    ui_screens_raw: list[str]
    test_scenario_doc: dict[str, Any]
    summary: dict[str, Any]
    status: str
