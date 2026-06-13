# FastAPI 요청 검증, DB 조회, 파일 다운로드 및 WorkflowState 초기화를 수행합니다.

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, cast
from urllib.parse import urlparse

from config.constants import DOCS_CODES, UPDATE_YN_VALUES
from config.settings import get_settings
from database.repositories.docs_detail_repository import DocsDetailRepository
from database.repositories.file_repository import FileRepository
from database.repositories.project_repository import ProjectRepository
from database.session import SessionLocal
from schemas.common.common_schema import DocsCode
from tools.result import ToolResult
from tools.storage.downloader import download_file
from workflow.state import WorkflowState


class ProjectRepositoryProtocol(Protocol):
    def exists_project(self, project_sn: int) -> bool: ...


class DocsDetailRepositoryProtocol(Protocol):
    def find_active_srs(self, project_sn: int) -> Any | None: ...

    def find_active_doc(self, project_sn: int, docs_cd: DocsCode) -> Any | None: ...

    def update_docs_status_generating(self, project_sn: int, docs_cd: DocsCode) -> None: ...

    def update_docs_status_failed(
        self,
        project_sn: int,
        docs_cd: DocsCode,
        error_message: str,
    ) -> None: ...


class FileRepositoryProtocol(Protocol):
    def find_file_by_sn(self, file_sn: int) -> Any | None: ...

    def find_files_by_sn_list(self, file_sn_list: list[int]) -> list[Any]: ...


@dataclass(frozen=True)
class RequestPreprocessDependencies:
    project_repository: ProjectRepositoryProtocol
    docs_detail_repository: DocsDetailRepositoryProtocol
    file_repository: FileRepositoryProtocol
    downloader: Callable[..., ToolResult]


class PreprocessError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def request_preprocess_node(
    state: WorkflowState,
    dependencies: RequestPreprocessDependencies | None = None,
) -> WorkflowState:
    """요청을 검증하고 Supervisor 진입 전 WorkflowState를 구성합니다."""

    session = None
    if dependencies is None:
        session = SessionLocal()
        dependencies = RequestPreprocessDependencies(
            project_repository=ProjectRepository(session),
            docs_detail_repository=DocsDetailRepository(session),
            file_repository=FileRepository(session),
            downloader=download_file,
        )

    result = _initialize_state(state)
    try:
        _validate_request(result)
        _validate_project(result, dependencies.project_repository)
        result["input_file_paths"] = _download_file_sn_list(
            result["file_list"], dependencies
        )
        result["input_image_paths"] = _download_file_sn_list(
            result["image_list"], dependencies
        )
        _resolve_required_documents(result, dependencies)
        dependencies.docs_detail_repository.update_docs_status_generating(
            result["project_sn"],
            result["docs_cd"],
        )
        return result
    except PreprocessError as exc:
        return _to_failed_state(result, dependencies.docs_detail_repository, exc)
    except Exception as exc:
        message = str(exc) or f"{type(exc).__name__}가 발생했습니다."
        return _to_failed_state(
            result,
            dependencies.docs_detail_repository,
            PreprocessError("PREPROCESS_FAILED", message),
        )
    finally:
        if session is not None:
            session.close()


def _initialize_state(state: WorkflowState) -> WorkflowState:
    return {
        "project_sn": state.get("project_sn"),  # type: ignore[typeddict-item]
        "docs_cd": state.get("docs_cd"),  # type: ignore[typeddict-item]
        "udt_yn": state.get("udt_yn"),  # type: ignore[typeddict-item]
        "status": "READY",
        "next_action": "SUPERVISOR",
        "file_list": list(state.get("file_list", [])),
        "image_list": list(state.get("image_list", [])),
        "etc": dict(state.get("etc", {})),
        "input_file_paths": [],
        "input_image_paths": [],
        "base_rfp_path": None,
        "base_requirement_json_path": None,
        "erd_file_path": None,
        "interface_file_path": None,
        "existing_output_path": None,
        "agent_outputs": {},
        "execution_plan": {},
        "current_round": 0,
        "max_round": get_settings().max_round,
        "supervisor_decision": None,
        "validation_result": None,
        "final_document_json": None,
        "export_result": None,
        "cleanup_result": None,
        "warnings": [],
        "errors": [],
    }


def _validate_request(state: WorkflowState) -> None:
    missing = [
        field for field in ("project_sn", "docs_cd", "udt_yn") if state.get(field) is None
    ]
    if missing:
        raise PreprocessError(
            "MISSING_REQUIRED_FIELD",
            f"필수 요청값이 없습니다: {', '.join(missing)}",
        )
    if state["docs_cd"] not in DOCS_CODES:
        raise PreprocessError("INVALID_DOCS_CD", f"허용되지 않은 docs_cd: {state['docs_cd']}")
    if state["udt_yn"] not in UPDATE_YN_VALUES:
        raise PreprocessError("INVALID_UDT_YN", f"허용되지 않은 udt_yn: {state['udt_yn']}")


def _validate_project(
    state: WorkflowState,
    repository: ProjectRepositoryProtocol,
) -> None:
    if not repository.exists_project(state["project_sn"]):
        raise PreprocessError("PROJECT_NOT_FOUND", "프로젝트를 찾을 수 없습니다.")


def _resolve_required_documents(
    state: WorkflowState,
    dependencies: RequestPreprocessDependencies,
) -> None:
    project_sn = state["project_sn"]
    docs_cd = state["docs_cd"]

    if state["udt_yn"] == "Y":
        if not state["file_list"]:
            raise PreprocessError(
                "MEETING_FILE_REQUIRED",
                "수정 모드에는 회의록 file_list가 필요합니다.",
            )
        active_doc = dependencies.docs_detail_repository.find_active_doc(project_sn, docs_cd)
        state["existing_output_path"] = _download_active_doc(active_doc, dependencies)
        return

    if docs_cd == "SRS":
        if not state["input_file_paths"]:
            raise PreprocessError("RFP_FILE_REQUIRED", "SRS 신규 생성에는 RFP 파일이 필요합니다.")
        state["base_rfp_path"] = state["input_file_paths"][0]
        return

    active_srs = dependencies.docs_detail_repository.find_active_srs(project_sn)
    state["base_requirement_json_path"] = _download_active_doc(active_srs, dependencies)

    if docs_cd == "DB":
        active_erd = dependencies.docs_detail_repository.find_active_doc(
            project_sn, cast(DocsCode, "ERD")
        )
        state["erd_file_path"] = _download_active_doc(active_erd, dependencies)
    elif docs_cd == "TS":
        active_interface = dependencies.docs_detail_repository.find_active_doc(
            project_sn, cast(DocsCode, "INTERFACE")
        )
        state["interface_file_path"] = _download_active_doc(active_interface, dependencies)


def _download_file_sn_list(
    file_sn_list: list[int],
    dependencies: RequestPreprocessDependencies,
) -> list[str]:
    if not file_sn_list:
        return []

    records = dependencies.file_repository.find_files_by_sn_list(file_sn_list)
    records_by_sn = {_read_value(record, "file_sn"): record for record in records}
    missing = [file_sn for file_sn in file_sn_list if file_sn not in records_by_sn]
    if missing:
        raise PreprocessError("FILE_NOT_FOUND", f"파일 정보를 찾을 수 없습니다: {missing}")
    return [_download_record(records_by_sn[file_sn], dependencies) for file_sn in file_sn_list]


def _download_active_doc(
    docs_detail: Any | None,
    dependencies: RequestPreprocessDependencies,
) -> str:
    if docs_detail is None:
        raise PreprocessError("ACTIVE_DOC_NOT_FOUND", "필수 활성 산출물을 찾을 수 없습니다.")
    file_sn = _read_value(docs_detail, "file_sn")
    if file_sn is None:
        raise PreprocessError("ACTIVE_DOC_FILE_MISSING", "활성 산출물에 file_sn이 없습니다.")
    file_record = dependencies.file_repository.find_file_by_sn(file_sn)
    if file_record is None:
        raise PreprocessError("FILE_NOT_FOUND", f"파일 정보를 찾을 수 없습니다: {file_sn}")
    return _download_record(file_record, dependencies)


def _download_record(
    file_record: Any,
    dependencies: RequestPreprocessDependencies,
) -> str:
    file_path = _read_value(file_record, "file_path")
    s3_key = _read_value(file_record, "s3_key")
    file_name = _read_value(file_record, "file_nm") or _read_value(file_record, "file_name")

    if not s3_key and isinstance(file_path, str) and file_path.startswith("s3://"):
        parsed = urlparse(file_path)
        s3_key = parsed.path.lstrip("/")
        file_path = None

    download_result = dependencies.downloader(
        file_path=file_path,
        s3_key=s3_key,
        file_name=file_name,
    )
    if not download_result["success"]:
        error = download_result["error"] or {}
        raise PreprocessError(
            str(error.get("code", "DOWNLOAD_FAILED")),
            str(error.get("message", "파일 다운로드에 실패했습니다.")),
        )
    return str(download_result["data"]["local_file_path"])


def _to_failed_state(
    state: WorkflowState,
    repository: DocsDetailRepositoryProtocol,
    error: PreprocessError,
) -> WorkflowState:
    state["status"] = "FAILED"
    state["next_action"] = "END"
    state["errors"].append({"code": error.code, "message": error.message})
    if state.get("project_sn") is not None and state.get("docs_cd") in DOCS_CODES:
        try:
            repository.update_docs_status_failed(
                state["project_sn"],
                state["docs_cd"],
                error.message,
            )
        except Exception:
            pass
    return state


def _read_value(record: Any, field_name: str) -> Any:
    if isinstance(record, dict):
        return record.get(field_name)
    return getattr(record, field_name, None)
