import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import urlparse

from config.constants import DOCS_CODES, FILE_CODE_RFP, UPDATE_YN_VALUES, normalize_docs_cd
from config.logging_config import get_logger
from config.logging_context import bind_state_log_extra
from config.settings import get_settings
from database.repositories.docs_detail_repository import DocsDetailRepository
from database.repositories.file_repository import FileRepository
from database.repositories.project_repository import ProjectRepository
from database.session import SessionLocal
from schemas.common.common_schema import DocsCode
from tools.result import ToolResult
from tools.storage.downloader import download_file
from workflow.state import WorkflowState


logger = get_logger("workflow.nodes.request_preprocess_node")


class ProjectRepositoryProtocol(Protocol):
    def exists_project(self, project_sn: int) -> bool: ...


class DocsDetailRepositoryProtocol(Protocol):
    def find_active_srs(self, project_sn: int) -> Any | None: ...

    def find_active_doc(self, project_sn: int, docs_cd: DocsCode) -> Any | None: ...
    def find_update_detail_context(
        self,
        project_sn: int,
        docs_cd: DocsCode,
        request_docs_detail_sn: int,
    ) -> dict[str, Any] | None: ...

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
        _log_info(result, "preprocess_start", "Request preprocessing started")
        _log_info(result, "preprocess_validate_request", "Validating request payload")
        _validate_request(result)

        _log_info(result, "preprocess_validate_project", "Validating project")
        _validate_project(result, dependencies.project_repository)

        _log_info(result, "preprocess_download_files", "Resolving input files")
        file_records = _find_file_sn_records(result["file_list"], dependencies)
        _validate_file_list_policy(result, file_records)
        result["input_file_paths"] = _download_file_records(
            result["file_list"],
            file_records,
            dependencies,
            result,
        )
        result["base_rfp_path"] = _select_downloaded_rfp_path(
            result["file_list"],
            file_records,
            result["input_file_paths"],
        )

        _log_info(result, "preprocess_download_images", "Resolving input images")
        result["input_image_paths"] = _download_image_paths(result["image_list"], dependencies, result)

        _log_info(
            result,
            "preprocess_resolve_required_documents",
            "Resolving prerequisite documents",
        )
        _resolve_required_documents(result, dependencies)

        _log_info(result, "preprocess_mark_generating", "Marking document as generating")
        _try_mark_docs_generating(result, dependencies.docs_detail_repository)

        _log_info(
            result,
            "preprocess_complete",
            "Request preprocessing completed files=%s images=%s",
            len(result["input_file_paths"]),
            len(result["input_image_paths"]),
        )
        return result

    except PreprocessError as exc:
        _log_warning(
            result,
            "preprocess_failed",
            "Request preprocessing failed code=%s",
            exc.code,
        )
        return _to_failed_state(result, dependencies.docs_detail_repository, exc)

    except Exception as exc:
        logger.exception(
            "Request preprocessing raised an unexpected exception",
            extra=bind_state_log_extra(result, "preprocess_failed"),
        )
        message = str(exc) or f"{type(exc).__name__} raised during preprocessing."
        return _to_failed_state(
            result,
            dependencies.docs_detail_repository,
            PreprocessError("PREPROCESS_FAILED", message),
        )

    finally:
        if session is not None:
            session.close()


def _initialize_state(state: WorkflowState) -> WorkflowState:
    settings = get_settings()
    workflow_temp_dir = _workflow_temp_dir(state, settings.input_dir)
    return {
        "project_sn": state.get("project_sn"),  # type: ignore[typeddict-item]
        "docs_cd": normalize_docs_cd(state.get("docs_cd")) if state.get("docs_cd") is not None else None,  # type: ignore[typeddict-item]
        "udt_yn": str(state.get("udt_yn")).upper() if state.get("udt_yn") is not None else None,  # type: ignore[typeddict-item]
        "docs_sn": state.get("docs_sn"),
        "request_docs_detail_sn": state.get("request_docs_detail_sn"),
        "before_docs_detail_sn": None,
        "status": "READY",
        "next_action": "SUPERVISOR",
        "file_list": list(state.get("file_list", [])),
        "image_list": list(state.get("image_list", [])),
        "etc": dict(state.get("etc", {})),
        "workflow_temp_dir": str(workflow_temp_dir),
        "input_file_paths": [],
        "input_image_paths": [],
        "base_rfp_path": None,
        "base_requirement_json_path": None,
        "erd_file_path": None,
        "interface_file_path": None,
        "existing_output_path": None,
        "requested_output_path": None,
        # ARCH 수정 모드에서만 기존 산출물 JSON을 적재합니다.
        # 다른 산출물은 기존처럼 existing_output_path 기반 흐름을 유지합니다.
        "existing_output_raw_json": None,
        "requested_output_raw_json": None,
        "agent_outputs": {},
        "execution_plan": {},
        "current_round": 0,
        "max_round": settings.max_round,
        "supervisor_decision": None,
        "repair_history": [],
        "current_repair_instruction": None,
        "repair_round": 0,
        "max_repair_round": settings.max_round,
        "validation_result": None,
        "final_document_json": None,
        "export_result": None,
        "cleanup_result": None,
        "warnings": [],
        "errors": [],
    }


def _workflow_temp_dir(state: WorkflowState, input_dir: Path) -> Path:
    identifier = (
        (state.get("etc") or {}).get("request_id")
        or (state.get("etc") or {}).get("job_id")
        or state.get("request_id")
        or state.get("job_id")
        or f"{state.get('project_sn') or 'project'}_{state.get('docs_cd') or 'docs'}_{id(state)}"
    )
    safe_identifier = "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in str(identifier)
    ).strip("_")
    return (input_dir / (safe_identifier or "workflow")).resolve()


def _validate_request(state: WorkflowState) -> None:
    missing = [
        field for field in ("project_sn", "docs_cd", "udt_yn") if state.get(field) is None
    ]
    if missing:
        raise PreprocessError(
            "MISSING_REQUIRED_FIELD",
            f"Missing required request fields: {', '.join(missing)}",
        )

    if state["docs_cd"] not in DOCS_CODES:
        raise PreprocessError("INVALID_DOCS_CD", f"Unsupported docs_cd: {state['docs_cd']}")

    if state["udt_yn"] not in UPDATE_YN_VALUES:
        raise PreprocessError("INVALID_UDT_YN", f"Unsupported udt_yn: {state['udt_yn']}")


def _validate_project(
    state: WorkflowState,
    repository: ProjectRepositoryProtocol,
) -> None:
    if not repository.exists_project(state["project_sn"]):
        raise PreprocessError("PROJECT_NOT_FOUND", "Project could not be found.")


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
                "Update mode requires meeting files in file_list.",
            )

        request_detail_sn = state.get("request_docs_detail_sn")
        if request_detail_sn:
            context = dependencies.docs_detail_repository.find_update_detail_context(
                project_sn,
                docs_cd,
                int(request_detail_sn),
            )
            if context is None or context.get("before") is None:
                raise PreprocessError(
                    "UPDATE_DETAIL_CONTEXT_NOT_FOUND",
                    "수정 전/후 docs_detail 문서 쌍을 찾을 수 없습니다.",
                )
            state["docs_sn"] = context["docs_sn"]
            state["before_docs_detail_sn"] = _read_value(
                context["before"], "docs_detail_sn"
            )
            state["existing_output_path"] = _download_required_document(
                context["before"],
                dependencies,
                state,
                missing_code="BEFORE_OUTPUT_NOT_FOUND",
                missing_message="수정 전 ERD 문서를 찾을 수 없습니다.",
            )
            state["requested_output_path"] = _download_required_document(
                context["requested"],
                dependencies,
                state,
                missing_code="REQUESTED_OUTPUT_NOT_FOUND",
                missing_message="승인 요청 ERD 문서를 찾을 수 없습니다.",
            )
            return

        active_doc = (
            dependencies.docs_detail_repository.find_active_srs(project_sn)
            if docs_cd == "SRS"
            else dependencies.docs_detail_repository.find_active_doc(project_sn, docs_cd)
        )

        # ARCH 수정 모드에서만 docs_dtl_cn에 저장된 기존 산출물 JSON을 state에 싣습니다.
        # 다른 산출물 수정 흐름에는 영향이 없도록 docs_cd == "ARCH" 조건으로 제한합니다.
        if docs_cd == "ARCH":
            raw_value = _read_value(active_doc, "docs_dtl_cn")
            print("[ARCH_PREPROCESS_DEBUG] docs_dtl_cn type =", type(raw_value))
            print("[ARCH_PREPROCESS_DEBUG] docs_dtl_cn length =", len(raw_value) if raw_value else None)

            existing_output_raw_json = _read_docs_detail_json(active_doc)

            print("[ARCH_PREPROCESS_DEBUG] existing_output_raw_json loaded =", bool(existing_output_raw_json))
            print(
                "[ARCH_PREPROCESS_DEBUG] existing_output_raw_json keys =",
                list(existing_output_raw_json.keys()) if isinstance(existing_output_raw_json, dict) else None,
            )

            if existing_output_raw_json:
                state["existing_output_raw_json"] = existing_output_raw_json
                _log_info(
                    state,
                    "preprocess_existing_output_raw_json",
                    "Existing ARCH output JSON loaded from docs_dtl_cn",
                )
            else:
                state["warnings"].append(
                    {
                        "code": "EXISTING_ARCH_OUTPUT_JSON_EMPTY",
                        "message": "Existing ARCH document JSON was not found in docs_dtl_cn. Falling back to existing output file path.",
                    }
                )

        state["existing_output_path"] = _download_required_document(
            active_doc,
            dependencies,
            state,
            missing_code="EXISTING_OUTPUT_NOT_FOUND",
            missing_message="Existing generated document could not be found for update mode.",
        )
        return

    if docs_cd == "SRS":
        if not state["base_rfp_path"]:
            raise PreprocessError("RFP_FILE_REQUIRED", "SRS generation requires an RFP file.")
        return

    active_srs = dependencies.docs_detail_repository.find_active_srs(project_sn)
    state["base_requirement_json_path"] = _download_required_document(
        active_srs,
        dependencies,
        state,
        missing_code="BASE_REQUIREMENT_JSON_NOT_FOUND",
        missing_message="Latest requirement JSON could not be found for this project.",
    )

    if docs_cd == "DB":
        active_erd = dependencies.docs_detail_repository.find_active_doc(
            project_sn,
            cast(DocsCode, "ERD"),
        )
        state["erd_file_path"] = _download_required_document(
            active_erd,
            dependencies,
            state,
            missing_code="ACTIVE_ERD_NOT_FOUND",
            missing_message="Latest ERD document is required before DB generation.",
        )

    elif docs_cd == "TS":
        active_interface = dependencies.docs_detail_repository.find_active_interface_json(project_sn)
        if active_interface is None:
            # 하위호환: INTERFACE JSON export가 도입되기 전에 이미 생성된 프로젝트는
            # JSON 레코드가 없으므로 기존 docx로 폴백한다.
            # document_merge_agent의 parse_artifact()는 .docx/.json 둘 다 처리 가능하므로
            # 다운스트림(TS) 쪽 추가 분기는 필요 없다.
            active_interface = dependencies.docs_detail_repository.find_active_doc(
                project_sn,
                cast(DocsCode, "INTERFACE"),
            )
        state["interface_file_path"] = _download_required_document(
            active_interface,
            dependencies,
            state,
            missing_code="ACTIVE_INTERFACE_NOT_FOUND",
            missing_message="Latest INTERFACE document is required before TS generation.",
        )

    elif docs_cd == "INTERFACE" and not state["input_image_paths"]:
        state["warnings"].append(
            {
                "code": "INTERFACE_IMAGE_LIST_EMPTY",
                "message": "INTERFACE generation can continue, but image_list is empty.",
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
        raise PreprocessError("FILE_NOT_FOUND", f"File records could not be found: {missing}")

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
            raise PreprocessError("RFP_FILE_REQUIRED", "SRS generation requires an RFP file.")
        return

    if rfp_file_sns:
        raise PreprocessError(
            "RFP_FILE_NOT_ALLOWED",
            f"RFP files are only allowed for SRS generation: {rfp_file_sns}",
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
    state: WorkflowState,
) -> list[str]:
    return [_download_record(records_by_sn[file_sn], dependencies, state) for file_sn in file_sn_list]


def _download_image_paths(
    image_list: list[str],
    dependencies: RequestPreprocessDependencies,
    state: WorkflowState,
) -> list[str]:
    downloaded_paths: list[str] = []

    for image_path in image_list:
        source = str(image_path).strip()
        if not source:
            raise PreprocessError("IMAGE_PATH_EMPTY", "image_list contains an empty path.")

        if source.startswith(("s3://", "http://", "https://")):
            record = {"file_path": source}
        else:
            record = {"s3_key": source}

        downloaded_paths.append(_download_record(record, dependencies, state))

    return downloaded_paths


def _download_active_doc(
    docs_detail: Any | None,
    dependencies: RequestPreprocessDependencies,
    state: WorkflowState,
) -> str:
    if docs_detail is None:
        raise PreprocessError("ACTIVE_DOC_NOT_FOUND", "Active document could not be found.")

    docs_path = _read_value(docs_detail, "docs_path") or _read_value(docs_detail, "file_path")

    if docs_path:
        return _download_record(
            {
                "file_path": docs_path,
                "file_nm": _read_value(docs_detail, "file_nm")
                or str(docs_path).replace("\\", "/").split("/")[-1],
            },
            dependencies,
            state,
        )

    file_sn = _read_value(docs_detail, "file_sn")
    if file_sn is None:
        raise PreprocessError(
            "ACTIVE_DOC_FILE_MISSING",
            "Active document is missing both docs_path and file_sn.",
        )

    file_record = dependencies.file_repository.find_file_by_sn(file_sn)
    if file_record is None:
        raise PreprocessError("FILE_NOT_FOUND", f"File record could not be found: {file_sn}")

    return _download_record(file_record, dependencies, state)


def _download_required_document(
    record: Any | None,
    dependencies: RequestPreprocessDependencies,
    state: WorkflowState,
    *,
    missing_code: str,
    missing_message: str,
) -> str:
    if record is None:
        raise PreprocessError(missing_code, missing_message)

    return _download_active_doc(record, dependencies, state)


def _read_docs_detail_json(docs_detail: Any | None) -> dict[str, Any] | None:
    if docs_detail is None:
        return None

    value = _read_value(docs_detail, "docs_dtl_cn")
    if not value:
        return None

    try:
        if isinstance(value, memoryview):
            text_value = value.tobytes().decode("utf-8")
        elif isinstance(value, bytearray):
            text_value = bytes(value).decode("utf-8")
        elif isinstance(value, bytes):
            text_value = value.decode("utf-8")
        elif isinstance(value, dict):
            return value
        else:
            text_value = str(value)

        parsed = json.loads(text_value)
        return parsed if isinstance(parsed, dict) else None

    except Exception as exc:
        logger.warning("Failed to parse docs_dtl_cn as JSON: %s", exc)
        return None


def _download_record(
    file_record: Any,
    dependencies: RequestPreprocessDependencies,
    state: WorkflowState,
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
        destination_dir=state.get("workflow_temp_dir"),
    )

    if not download_result["success"]:
        error = download_result["error"] or {}
        raise PreprocessError(
            str(error.get("code", "DOWNLOAD_FAILED")),
            str(error.get("message", "File download failed.")),
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
                    "message": str(exc) or "Failed to update docs status.",
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
                "message": str(exc) or "Failed to update docs status.",
            }
        )


def _read_value(record: Any, field_name: str) -> Any:
    if isinstance(record, dict):
        return record.get(field_name)

    return getattr(record, field_name, None)


def _log_info(state: WorkflowState, phase: str, message: str, *args: Any) -> None:
    logger.info(message, *args, extra=bind_state_log_extra(state, phase))


def _log_warning(state: WorkflowState, phase: str, message: str, *args: Any) -> None:
    logger.warning(message, *args, extra=bind_state_log_extra(state, phase))
