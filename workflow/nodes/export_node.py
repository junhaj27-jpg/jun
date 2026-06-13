# 최종 문서 JSON을 기반으로 DOCX 파일을 생성하고 저장소 및 DB에 등록합니다.

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from config.constants import DOCS_CODES
from config.settings import Settings, get_settings
from database.repositories.docs_detail_repository import DocsDetailRepository
from database.repositories.file_repository import FileRepository
from database.session import SessionLocal
from schemas.common.common_schema import DocsCode
from tools.docx.docx_exporter import export_docx
from tools.docx.template_mapper import map_document_to_template
from tools.result import ToolResult
from tools.storage.uploader import upload_file
from workflow.state import WorkflowState


class FileRepositoryProtocol(Protocol):
    def insert_file(
        self, *, file_nm: str, file_path: str, file_size: int, file_extn: str
    ) -> Any: ...


class DocsDetailRepositoryProtocol(Protocol):
    def deactivate_active_doc(self, project_sn: int, docs_cd: DocsCode) -> None: ...

    def insert_docs_detail(
        self,
        *,
        project_sn: int,
        docs_cd: DocsCode,
        file_sn: int,
        use_yn: str = "Y",
        status: str = "DONE",
    ) -> Any: ...

    def update_docs_status_done(self, project_sn: int, docs_cd: DocsCode) -> None: ...

    def update_docs_status_failed(
        self, project_sn: int, docs_cd: DocsCode, error_message: str
    ) -> None: ...


@dataclass(frozen=True)
class ExportDependencies:
    file_repository: FileRepositoryProtocol
    docs_detail_repository: DocsDetailRepositoryProtocol
    template_mapper: Callable[[dict[str, Any], str], ToolResult] = map_document_to_template
    docx_exporter: Callable[..., ToolResult] = export_docx
    uploader: Callable[..., ToolResult] = upload_file
    settings: Settings | None = None


class ExportError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def export_node(
    state: WorkflowState,
    dependencies: ExportDependencies | None = None,
) -> WorkflowState:
    """최종 JSON을 DOCX로 내보내고 활성 산출물 버전을 등록합니다."""

    session = None
    if dependencies is None:
        session = SessionLocal()
        dependencies = ExportDependencies(
            file_repository=FileRepository(session),
            docs_detail_repository=DocsDetailRepository(session),
        )

    settings = dependencies.settings or get_settings()
    try:
        project_sn, docs_cd, final_document_json = _validate_state(state)
        mapped = dependencies.template_mapper(final_document_json, docs_cd)
        export_payload = _unwrap_tool_result(mapped, "EXPORT_MAPPING_FAILED")

        file_name = _build_file_name(project_sn, docs_cd)
        local_file_path = str((settings.output_dir / file_name).resolve())
        template_path = str((Path("templates") / f"{docs_cd.lower()}_template.docx").resolve())
        generated = dependencies.docx_exporter(
            export_payload,
            local_file_path,
            template_path=template_path,
        )
        generated_data = _unwrap_tool_result(generated, "DOCX_EXPORT_FAILED")

        upload_kwargs: dict[str, Any] = {"settings": settings}
        if settings.s3_bucket:
            upload_kwargs["s3_key"] = f"project/{project_sn}/{docs_cd}/{file_name}"
        else:
            upload_kwargs["storage_path"] = local_file_path
        uploaded = dependencies.uploader(local_file_path, **upload_kwargs)
        uploaded_data = _unwrap_tool_result(uploaded, "UPLOAD_FAILED")
        storage_file_path = str(uploaded_data["storage_file_path"])

        file_record = dependencies.file_repository.insert_file(
            file_nm=file_name,
            file_path=storage_file_path,
            file_size=int(generated_data["file_size"]),
            file_extn="docx",
        )
        file_sn = _read_file_sn(file_record)
        if state.get("udt_yn") == "Y":
            dependencies.docs_detail_repository.deactivate_active_doc(project_sn, docs_cd)
        dependencies.docs_detail_repository.insert_docs_detail(
            project_sn=project_sn,
            docs_cd=docs_cd,
            file_sn=file_sn,
            use_yn="Y",
            status="DONE",
        )
        dependencies.docs_detail_repository.update_docs_status_done(project_sn, docs_cd)
        if session is not None:
            session.commit()

        state["status"] = "DONE"
        state["next_action"] = "END"
        state["export_result"] = {
            "status": "SUCCESS",
            "project_sn": project_sn,
            "docs_cd": docs_cd,
            "file_sn": file_sn,
            "local_file_path": local_file_path,
            "storage_file_path": storage_file_path,
            "file_name": file_name,
            "file_size": int(generated_data["file_size"]),
            "warnings": [],
            "errors": [],
        }
        return state
    except Exception as exc:
        if session is not None:
            session.rollback()
        error = exc if isinstance(exc, ExportError) else ExportError("EXPORT_FAILED", str(exc))
        _mark_failed(state, dependencies.docs_detail_repository, error)
        return state
    finally:
        if session is not None:
            session.close()


def _validate_state(state: WorkflowState) -> tuple[int, DocsCode, dict[str, Any]]:
    project_sn = state.get("project_sn")
    docs_cd = state.get("docs_cd")
    final_document_json = state.get("final_document_json")
    if not isinstance(project_sn, int):
        raise ExportError("EXPORT_PROJECT_SN_MISSING", "project_sn이 필요합니다.")
    if docs_cd not in DOCS_CODES:
        raise ExportError("EXPORT_DOCS_CD_INVALID", "유효한 docs_cd가 필요합니다.")
    if not isinstance(final_document_json, dict):
        raise ExportError("FINAL_DOCUMENT_JSON_MISSING", "final_document_json이 필요합니다.")
    return project_sn, docs_cd, final_document_json


def _unwrap_tool_result(result: ToolResult, default_code: str) -> Any:
    if result["success"]:
        return result["data"]
    error = result.get("error") or {}
    raise ExportError(str(error.get("code", default_code)), str(error.get("message", default_code)))


def _build_file_name(project_sn: int, docs_cd: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    return f"{docs_cd}_{project_sn}_{timestamp}.docx"


def _read_file_sn(record: Any) -> int:
    value = record.get("file_sn") if isinstance(record, dict) else getattr(record, "file_sn", record)
    if not isinstance(value, int):
        raise ExportError("FILE_SN_MISSING", "tbl_file 등록 결과에 file_sn이 없습니다.")
    return value


def _mark_failed(
    state: WorkflowState,
    repository: DocsDetailRepositoryProtocol,
    error: ExportError,
) -> None:
    state["status"] = "FAILED"
    state["next_action"] = "END"
    state["errors"] = list(state.get("errors", []))
    state["errors"].append({"code": error.code, "message": error.message})
    state["export_result"] = {
        "status": "FAILED",
        "project_sn": state.get("project_sn"),
        "docs_cd": state.get("docs_cd"),
        "file_sn": None,
        "local_file_path": "",
        "storage_file_path": "",
        "file_name": "",
        "file_size": 0,
        "warnings": [],
        "errors": [{"code": error.code, "message": error.message}],
    }
    if isinstance(state.get("project_sn"), int) and state.get("docs_cd") in DOCS_CODES:
        try:
            repository.update_docs_status_failed(
                state["project_sn"], state["docs_cd"], error.message
            )
        except Exception:
            pass
