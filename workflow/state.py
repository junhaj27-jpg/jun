# LangGraph 워크플로우에서 사용하는 상태를 정의합니다.

from typing import Any, TypedDict

from schemas.common.common_schema import DocsCode, NextAction, UpdateYn, WorkflowStatus
from schemas.common.file_schema import FileSn


class WorkflowState(TypedDict, total=False):
    # 1. Request 정보
    project_sn: int
    docs_cd: DocsCode
    udt_yn: UpdateYn
    status: WorkflowStatus
    next_action: NextAction | None

    # 2. FastAPI Input
    file_list: list[FileSn]
    image_list: list[FileSn]
    etc: dict[str, Any]

    # 3. Local Resource
    input_file_paths: list[str]
    input_image_paths: list[str]

    # 4. 기준 문서 / 참조 산출물 경로
    base_rfp_path: str | None
    base_requirement_json_path: str | None
    erd_file_path: str | None
    interface_file_path: str | None
    existing_output_path: str | None

    # 5. Agent Output
    agent_outputs: dict[str, Any]

    # 6. Supervisor
    execution_plan: dict[str, Any]
    current_round: int
    max_round: int
    supervisor_decision: dict[str, Any] | None

    # 7. Validation
    validation_result: dict[str, Any] | None

    # 8. Reduce
    final_document_json: dict[str, Any] | None

    # 9. Export
    export_result: dict[str, Any] | None

    # 10. Cleanup
    cleanup_result: dict[str, Any] | None

    # 11. Error
    warnings: list[dict[str, Any]]
    errors: list[dict[str, Any]]
