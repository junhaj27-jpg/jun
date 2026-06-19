# FastAPI 요청 검증, DB 조회, 파일 다운로드 및 WorkflowState 초기화를 수행합니다.

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, cast
from urllib.parse import urlparse

from config.constants import DOCS_CODES, FILE_CODE_RFP, UPDATE_YN_VALUES, normalize_docs_cd
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

    def ensure_docs_status_generating(self, project_sn: int, docs_cd: DocsCode) -> Any: ...

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
        file_records = _find_file_sn_records(result["file_list"], dependencies)
        _validate_file_list_policy(result, file_records)
        result["input_file_paths"] = _download_file_records(
            result["file_list"], file_records, dependencies
        )
        result["base_rfp_path"] = _select_downloaded_rfp_path(
            result["file_list"], file_records, result["input_file_paths"]
        )
        result["input_image_paths"] = _download_image_paths(result["image_list"], dependencies)
        _resolve_required_documents(result, dependencies)
        _try_mark_docs_generating(result, dependencies.docs_detail_repository)
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
        "docs_cd": normalize_docs_cd(state.get("docs_cd")) if state.get("docs_cd") is not None else None,  # type: ignore[typeddict-item]
        "udt_yn": str(state.get("udt_yn")).upper() if state.get("udt_yn") is not None else None,  # type: ignore[typeddict-item]
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
        "repair_history": [],
        "current_repair_instruction": None,
        "repair_round": 0,
        "max_repair_round": 2,
        "agent_outputs_before_repair": {},
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
        active_doc = (
            dependencies.docs_detail_repository.find_active_srs(project_sn)
            if docs_cd == "SRS"
            else dependencies.docs_detail_repository.find_active_doc(project_sn, docs_cd)
        )
        state["existing_output_path"] = _download_required_document(
            active_doc,
            dependencies,
            missing_code="EXISTING_OUTPUT_NOT_FOUND",
            missing_message="수정 기준 기존 산출물을 찾을 수 없습니다.",
        )
        return

    if docs_cd == "SRS":
        if not state["base_rfp_path"]:
            raise PreprocessError("RFP_FILE_REQUIRED", "SRS 신규 생성에는 RFP 파일이 필요합니다.")
        return

    active_srs = dependencies.docs_detail_repository.find_active_srs(project_sn)
    state["base_requirement_json_path"] = _download_required_document(
        active_srs,
        dependencies,
        missing_code="BASE_REQUIREMENT_JSON_NOT_FOUND",
        missing_message="프로젝트 기준 요구사항 final JSON(FILE_REQ_DOC_JSON)을 찾을 수 없습니다.",
    )

    if docs_cd == "DB":
        active_erd = dependencies.docs_detail_repository.find_active_doc(
            project_sn, cast(DocsCode, "ERD")
        )
        state["erd_file_path"] = _download_required_document(
            active_erd,
            dependencies,
            missing_code="ACTIVE_ERD_NOT_FOUND",
            missing_message="DB 설계서 생성에 필요한 최신 ERD 산출물을 찾을 수 없습니다.",
        )
    elif docs_cd == "TS":
        active_interface = dependencies.docs_detail_repository.find_active_doc(
            project_sn, cast(DocsCode, "INTERFACE")
        )
        state["interface_file_path"] = _download_required_document(
            active_interface,
            dependencies,
            missing_code="ACTIVE_INTERFACE_NOT_FOUND",
            missing_message="통합시험 시나리오 생성에 필요한 최신 INTERFACE 산출물을 찾을 수 없습니다.",
        )
    elif docs_cd == "INTERFACE" and not state["input_image_paths"]:
        state["warnings"].append(
            {
                "code": "INTERFACE_IMAGE_LIST_EMPTY",
                "message": "INTERFACE 신규 생성 요청에 image_list가 없습니다. 후속 이미지 분석 단계에서 실패 또는 보완 요청이 발생할 수 있습니다.",
            }
        )


def _find_file_sn_records(
    file_sn_list: list[int],
    dependencies: RequestPreprocessDependencies,
) -> dict[int, Any]:
    if not file_sn_list:
        return {}

    records = dependencies.file_repository.find_files_by_sn_list(file_sn_list)
    records_by_sn = {_read_value(record, "file_sn"): record for record in records}
    missing = [file_sn for file_sn in file_sn_list if file_sn not in records_by_sn]
    if missing:
        raise PreprocessError("FILE_NOT_FOUND", f"파일 정보를 찾을 수 없습니다: {missing}")
    return records_by_sn


def _validate_file_list_policy(
    state: WorkflowState,
    file_records: dict[int, Any],
) -> None:
    rfp_file_sns = [
        file_sn
        for file_sn, record in file_records.items()
        if str(_read_value(record, "file_cd") or "").upper() == FILE_CODE_RFP
    ]
    if state["udt_yn"] != "N":
        return
    if state["docs_cd"] == "SRS":
        if not rfp_file_sns:
            raise PreprocessError("RFP_FILE_REQUIRED", "SRS 신규 생성에는 RFP 파일이 필요합니다.")
        return
    if rfp_file_sns:
        raise PreprocessError(
            "RFP_FILE_NOT_ALLOWED",
            f"SRS 외 산출물 신규 생성 요청에는 RFP 파일을 file_list로 전달할 수 없습니다: {rfp_file_sns}",
        )


def _select_downloaded_rfp_path(
    file_sn_list: list[int],
    file_records: dict[int, Any],
    downloaded_paths: list[str],
) -> str | None:
    for index, file_sn in enumerate(file_sn_list):
        record = file_records.get(file_sn)
        if str(_read_value(record, "file_cd") or "").upper() == FILE_CODE_RFP:
            return downloaded_paths[index]
    return None


def _download_file_records(
    file_sn_list: list[int],
    records_by_sn: dict[int, Any],
    dependencies: RequestPreprocessDependencies,
) -> list[str]:
    return [_download_record(records_by_sn[file_sn], dependencies) for file_sn in file_sn_list]


def _download_image_paths(
    image_list: list[str],
    dependencies: RequestPreprocessDependencies,
) -> list[str]:
    downloaded_paths: list[str] = []
    for image_path in image_list:
        source = str(image_path).strip()
        if not source:
            raise PreprocessError("IMAGE_PATH_EMPTY", "image_list에 빈 이미지 경로가 포함되어 있습니다.")
        if source.startswith(("s3://", "http://", "https://")):
            record = {"file_path": source}
        else:
            record = {"s3_key": source}
        downloaded_paths.append(_download_record(record, dependencies))
    return downloaded_paths


def _download_active_doc(
    docs_detail: Any | None,
    dependencies: RequestPreprocessDependencies,
) -> str:
    if docs_detail is None:
        raise PreprocessError("ACTIVE_DOC_NOT_FOUND", "필수 활성 산출물을 찾을 수 없습니다.")
    docs_path = _read_value(docs_detail, "docs_path") or _read_value(docs_detail, "file_path")
    if docs_path:
        return _download_record(
            {
                "file_path": docs_path,
                "file_nm": _read_value(docs_detail, "file_nm")
                or str(docs_path).replace("\\", "/").split("/")[-1],
            },
            dependencies,
        )
    file_sn = _read_value(docs_detail, "file_sn")
    if file_sn is None:
        raise PreprocessError("ACTIVE_DOC_FILE_MISSING", "활성 산출물에 docs_path 또는 file_sn이 없습니다.")
    file_record = dependencies.file_repository.find_file_by_sn(file_sn)
    if file_record is None:
        raise PreprocessError("FILE_NOT_FOUND", f"파일 정보를 찾을 수 없습니다: {file_sn}")
    return _download_record(file_record, dependencies)


def _download_required_document(
    record: Any | None,
    dependencies: RequestPreprocessDependencies,
    *,
    missing_code: str,
    missing_message: str,
) -> str:
    if record is None:
        raise PreprocessError(missing_code, missing_message)
    return _download_active_doc(record, dependencies)


def _download_record(
    file_record: Any,
    dependencies: RequestPreprocessDependencies,
) -> str:
    file_path = _read_value(file_record, "file_path")
    s3_key = _read_value(file_record, "s3_key")
    s3_bucket = _read_value(file_record, "s3_bucket")
    file_name = _read_value(file_record, "file_nm") or _read_value(file_record, "file_name")

    if not s3_key and isinstance(file_path, str) and file_path.startswith("s3://"):
        parsed = urlparse(file_path)
        s3_bucket = parsed.netloc
        s3_key = parsed.path.lstrip("/")
        file_path = None

    download_result = dependencies.downloader(
        file_path=file_path,
        s3_key=s3_key,
        s3_bucket=s3_bucket,
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
        except Exception as exc:
            state["errors"].append(
                {
                    "code": "DOCS_STATUS_UPDATE_FAILED",
                    "message": str(exc) or "산출물 상태 업데이트에 실패했습니다.",
                }
            )
    return state


def _try_mark_docs_generating(
    state: WorkflowState,
    repository: DocsDetailRepositoryProtocol,
) -> None:
    try:
        if state["udt_yn"] == "N" and hasattr(repository, "ensure_docs_status_generating"):
            repository.ensure_docs_status_generating(state["project_sn"], state["docs_cd"])
        else:
            repository.update_docs_status_generating(
                state["project_sn"],
                state["docs_cd"],
            )
    except Exception as exc:
        state["warnings"].append(
            {
                "code": "DOCS_STATUS_UPDATE_FAILED",
                "message": str(exc) or "산출물 상태 업데이트에 실패했습니다.",
            }
        )


def _read_value(record: Any, field_name: str) -> Any:
    if isinstance(record, dict):
        return record.get(field_name)
    return getattr(record, field_name, None)
