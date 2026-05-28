from typing import Any, Dict, List, TypedDict


class ArchitectureWorkflowState(TypedDict, total=False):
    requirement_json_path: str
    infra_spec_path: str
    output_json_path: str
    output_md_path: str | None
    output_docx_path: str
    output_image_path: str
    render_image: bool

    requirement_doc: Dict[str, Any]
    user_infra_spec: Dict[str, Any]
    analyzed_reqs: List[Dict[str, Any]]
    extracted_infra: Dict[str, Any]
    report_specs: str
    mermaid_script: str
    validation_result: Dict[str, Any]
    validation_errors: List[str]
    retry_count: int
    status: str
