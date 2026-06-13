from typing import Any, Dict, List, TypedDict


class DatabaseDesignWorkflowState(TypedDict, total=False):
    requirement_json_path: str
    erd_docx_path: str
    output_json_path: str
    output_docx_path: str
    use_rag: bool

    requirement_doc: Dict[str, Any]
    system_context: Dict[str, Any]
    erd: Dict[str, Any]
    database_design: Dict[str, Any]
    rag_context: Dict[str, Any]
    database_design_docx_path: str

    validation_errors: List[str]
    status: str
