from typing import Any, TypedDict

# 워크 플로우 상태 정의
class InterfaceWorkflowState(TypedDict, total=False):
    requirement_paths: str | list[str]
    image_paths: str | list[str]
    output_json_path: str
    output_docx_path: str
    work_dir: str
    max_images: int | None

    requirement_summary: dict[str, Any]
    image_file_paths: list[str]
    screen_specs: list[dict[str, Any]]
    ui_structure: list[dict[str, str]]
    integrated_json_path: str
    status: str
