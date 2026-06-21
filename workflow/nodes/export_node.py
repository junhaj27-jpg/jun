# 최종 문서 JSON을 기반으로 DOCX 파일을 생성하고 저장소 및 DB에 등록합니다.

import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from config.constants import DOCS_CODES, FILE_CODE_REQUIREMENT_JSON
from config.logging_config import get_logger
from config.logging_context import bind_state_log_extra
from config.settings import Settings, get_settings
from database.repositories.docs_detail_repository import DocsDetailRepository
from database.repositories.docs_repository import DocsRepository
from database.repositories.file_repository import FileRepository
from database.repositories.project_repository import ProjectRepository
from database.session import SessionLocal
from schemas.common.common_schema import DocsCode
from tools.docx.docx_exporter import export_docx
from tools.docx.template_mapper import map_document_to_template
from tools.result import ToolResult
from tools.storage.uploader import upload_file
from workflow.state import WorkflowState


logger = get_logger("workflow.nodes.export_node")


class FileRepositoryProtocol(Protocol):
    def insert_file(
        self,
        *,
        project_sn: int,
        file_cd: str,
        file_nm: str,
        file_path: str,
        file_size: int,
        file_ext: str | None = None,
        file_extn: str | None = None,
    ) -> Any: ...


class DocsDetailRepositoryProtocol(Protocol):
    def insert_docs_detail(
        self,
        *,
        project_sn: int,
        docs_cd: DocsCode,
        docs_path: str,
        file_sn: int | None = None,
        docs_dtl_cn: bytes | None = None,
        use_yn: str = "Y",
        status: str = "DONE",
    ) -> Any: ...

    def update_docs_status_done(self, project_sn: int, docs_cd: DocsCode) -> None: ...

    def update_docs_status_failed(
        self, project_sn: int, docs_cd: DocsCode, error_message: str
    ) -> None: ...


class ProjectRepositoryProtocol(Protocol):
    def find_project_by_sn(self, project_sn: int) -> Any | None: ...


class DocsRepositoryProtocol(Protocol):
    def find_project_docs_by_code(
        self,
        project_sn: int,
        docs_cd: DocsCode,
    ) -> Any | None: ...


@dataclass(frozen=True)
class ExportDependencies:
    file_repository: FileRepositoryProtocol
    docs_detail_repository: DocsDetailRepositoryProtocol
    project_repository: ProjectRepositoryProtocol | None = None
    docs_repository: DocsRepositoryProtocol | None = None
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
            project_repository=ProjectRepository(session),
            docs_repository=DocsRepository(session),
        )

    settings = dependencies.settings or get_settings()
    try:
        logger.info(
            "Export validation started",
            extra=bind_state_log_extra(state, "export_validate_state"),
        )
        project_sn, docs_cd, final_document_json = _validate_state(state)

        requirement_json_record = _export_requirement_json_if_needed(
            state=state,
            project_sn=project_sn,
            docs_cd=docs_cd,
            final_document_json=final_document_json,
            dependencies=dependencies,
            settings=settings,
        )

        export_document_json = _enrich_final_document_json_for_export(
            final_document_json=final_document_json,
            project_sn=project_sn,
            docs_cd=docs_cd,
            dependencies=dependencies,
        )

        mapped = dependencies.template_mapper(export_document_json, docs_cd)
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
        generated_local_file_path = str(generated_data.get("local_file_path") or local_file_path)
        generated_file_name = str(
            generated_data.get("file_name") or Path(generated_local_file_path).name
        )
        generated_file_size = int(generated_data["file_size"])

        upload_kwargs: dict[str, Any] = {"settings": settings}
        if settings.s3_bucket:
            upload_kwargs["s3_key"] = f"project/{project_sn}/{docs_cd}/{generated_file_name}"
        else:
            upload_kwargs["storage_path"] = generated_local_file_path

        logger.info(
            "Uploading exported document",
            extra=bind_state_log_extra(
                state,
                "export_upload",
                project_sn=project_sn,
                docs_cd=docs_cd,
            ),
        )

        uploaded = dependencies.uploader(generated_local_file_path, **upload_kwargs)
        uploaded_data = _unwrap_tool_result(uploaded, "UPLOAD_FAILED")
        storage_file_path = str(uploaded_data["storage_file_path"])

        # ARCH 산출물만 수정 모드에서 기존 구조 JSON을 재사용할 수 있도록 docs_dtl_cn에 저장합니다.
        # 다른 산출물은 기존 동작과 동일하게 docs_dtl_cn=None으로 유지합니다.
        docs_dtl_cn = (
            _serialize_docs_detail_content(export_document_json)
            if docs_cd == "ARCH"
            else None
        )

        dependencies.docs_detail_repository.insert_docs_detail(
            project_sn=project_sn,
            docs_cd=docs_cd,
            docs_path=storage_file_path,
            file_sn=None,
            docs_dtl_cn=docs_dtl_cn,
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
            "file_sn": None,
            "requirement_json_file_sn": (
                requirement_json_record.get("file_sn") if requirement_json_record else None
            ),
            "requirement_json_file_path": (
                requirement_json_record.get("storage_file_path") if requirement_json_record else ""
            ),
            "local_file_path": generated_local_file_path,
            "storage_file_path": storage_file_path,
            "file_name": generated_file_name,
            "file_size": generated_file_size,
            "warnings": [],
            "errors": [],
        }

        logger.info(
            "Export completed storage_file_path=%s",
            storage_file_path,
            extra=bind_state_log_extra(
                state,
                "export_complete",
                project_sn=project_sn,
                docs_cd=docs_cd,
            ),
        )
        return state

    except Exception as exc:
        if session is not None:
            session.rollback()

        error = exc if isinstance(exc, ExportError) else ExportError("EXPORT_FAILED", str(exc))
        _mark_failed(state, dependencies.docs_detail_repository, error)

        logger.exception(
            "Export failed code=%s",
            error.code,
            extra=bind_state_log_extra(state, "export_failed"),
        )
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


def _export_requirement_json_if_needed(
    *,
    state: WorkflowState,
    project_sn: int,
    docs_cd: DocsCode,
    final_document_json: dict[str, Any],
    dependencies: ExportDependencies,
    settings: Settings,
) -> dict[str, Any] | None:
    if docs_cd != "SRS":
        return None

    file_name = _build_json_file_name(project_sn, docs_cd)
    local_file_path = settings.output_dir / file_name
    local_file_path.parent.mkdir(parents=True, exist_ok=True)
    local_file_path.write_text(
        json.dumps(final_document_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    upload_kwargs: dict[str, Any] = {"settings": settings}
    if settings.s3_bucket:
        upload_kwargs["s3_key"] = f"project/{project_sn}/{docs_cd}/{file_name}"
    else:
        upload_kwargs["storage_path"] = str(local_file_path)

    uploaded = dependencies.uploader(str(local_file_path), **upload_kwargs)
    uploaded_data = _unwrap_tool_result(uploaded, "REQUIREMENT_JSON_UPLOAD_FAILED")
    storage_file_path = str(uploaded_data["storage_file_path"])

    file_record = dependencies.file_repository.insert_file(
        project_sn=project_sn,
        file_cd=FILE_CODE_REQUIREMENT_JSON,
        file_nm=file_name,
        file_path=storage_file_path,
        file_size=local_file_path.stat().st_size,
        file_ext="json",
    )

    return {
        "file_sn": _read_file_sn(file_record),
        "local_file_path": str(local_file_path),
        "storage_file_path": storage_file_path,
        "file_name": file_name,
        "file_size": local_file_path.stat().st_size,
    }


def _enrich_final_document_json_for_export(
    *,
    final_document_json: dict[str, Any],
    project_sn: int,
    docs_cd: DocsCode,
    dependencies: ExportDependencies,
) -> dict[str, Any]:
    export_document_json = deepcopy(final_document_json)
    metadata = _read_export_metadata(project_sn, docs_cd, dependencies)

    if not metadata:
        return export_document_json

    export_document_json.setdefault("metadata", {})
    if isinstance(export_document_json["metadata"], dict):
        export_document_json["metadata"].update(metadata)

    content_key_by_docs = {
        "SRS": "requirement_json_list",
        "INTERFACE": "interface_json_list",
        "TS": "integrated_test_scenario_json",
        "ERD": "erd_entity_json",
        "DB": "db_design_json",
        "ARCH": "architecture_document_json",
    }
    content_key = content_key_by_docs.get(docs_cd)
    content = export_document_json.get(content_key) if content_key else None

    if isinstance(content, dict):
        for key, value in metadata.items():
            content[key] = value

    return export_document_json


def _read_export_metadata(
    project_sn: int,
    docs_cd: DocsCode,
    dependencies: ExportDependencies,
) -> dict[str, str]:
    metadata: dict[str, str] = {}

    if dependencies.project_repository is not None:
        project = dependencies.project_repository.find_project_by_sn(project_sn)
        project_name = _pick_first(project, "prj_nm", "project_nm", "project_name", "system_name")
        if project_name:
            metadata["system_name"] = project_name
            metadata["project_name"] = project_name

    if dependencies.docs_repository is not None:
        docs = dependencies.docs_repository.find_project_docs_by_code(project_sn, docs_cd)
        docs_version = _pick_first(docs, "docs_ver", "version")
        if docs_version is not None:
            metadata["version"] = docs_version

    return metadata


def _pick_first(source: Any, *keys: str) -> str | None:
    if source is None:
        return None

    for key in keys:
        value = source.get(key) if isinstance(source, dict) else getattr(source, key, None)
        if value is not None:
            return str(value)

    return None


def _unwrap_tool_result(result: ToolResult, default_code: str) -> Any:
    if result["success"]:
        return result["data"]

    error = result.get("error") or {}
    raise ExportError(
        str(error.get("code", default_code)),
        str(error.get("message", default_code)),
    )


def _build_file_name(project_sn: int, docs_cd: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    return f"{docs_cd}_{project_sn}_{timestamp}.docx"


def _build_json_file_name(project_sn: int, docs_cd: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    return f"{docs_cd}_{project_sn}_{timestamp}.json"


def _serialize_docs_detail_content(document_json: dict[str, Any]) -> bytes:
    return json.dumps(
        document_json,
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


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
