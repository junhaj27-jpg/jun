from typing import Any, Dict, List, Optional, TypedDict


class ErdWorkflowState(TypedDict, total=False):
    prj_sn: int
    login_user_sn: int
    requirement_docs_sn: Optional[int]
    requirement_file_sn: Optional[int]
    meeting_file_sns: List[int]

    requirement_json_path: str
    use_llm: bool
    use_mermaid: bool
    fast_table: bool
    output_json_path: str
    output_docx_path: str
    save_to_db: bool
    save_image_file: bool

    requirement_path: Optional[str]
    meeting_file_paths: List[str]
    requirement_text: str
    meeting_text: str
    requirement_json: Dict[str, Any]
    requirement_doc: Dict[str, Any]
    system_context: Dict[str, Any]
    rag_context: Dict[str, Any]
    table_structure_json: Dict[str, Any]
    entity_candidate_json: Dict[str, Any]
    final_erd_json: Dict[str, Any]
    erd: Dict[str, Any]
    mermaid_script: str
    erd_image_path: str
    erd_docx_path: str
    docs_sn: Optional[int]
    docs_dtl_sn: Optional[int]
    erd_image_file_sn: Optional[int]

    validation_errors: List[str]
    retry_count: int
    status: str
