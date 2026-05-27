from typing import Any, Dict, List, TypedDict


class ErdWorkflowState(TypedDict, total=False):
    requirement_json_path: str
    use_llm: bool
    use_mermaid: bool
    fast_table: bool
    output_json_path: str
    output_docx_path: str

    requirement_doc: Dict[str, Any]
    system_context: Dict[str, Any]
    rag_context: Dict[str, Any]
    erd: Dict[str, Any]
    mermaid_script: str
    erd_docx_path: str

    validation_errors: List[str]
    retry_count: int
    status: str
