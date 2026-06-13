import shutil
from pathlib import Path
from typing import Any, Iterable

from config.settings import Settings, get_settings
from tools.result import ToolResult, error_result, success_result


def cleanup_paths(
    paths: Iterable[str],
    *,
    protected_paths: Iterable[str] = (),
    allowed_root: str | Path | None = None,
) -> ToolResult:
    """허용된 로컬 저장소 내부의 파일과 디렉터리만 삭제합니다."""

    root = Path(allowed_root or get_settings().local_storage_root).resolve()
    protected = {Path(path).resolve() for path in protected_paths if path}
    removed: list[str] = []
    skipped: list[str] = []
    errors: list[dict[str, str]] = []

    for raw_path in dict.fromkeys(path for path in paths if path):
        try:
            target = Path(raw_path).resolve()
            if target != root and root not in target.parents:
                raise ValueError(f"허용된 저장소 외부 경로입니다: {target}")
            if _is_protected(target, protected):
                skipped.append(str(target))
                continue
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
            removed.append(str(target))
        except Exception as exc:
            errors.append({"path": raw_path, "message": str(exc)})

    if errors:
        return error_result(
            "CLEANUP_PARTIAL_FAILED",
            "일부 경로 정리에 실패했습니다.",
            {"errors": errors, "removed_paths": removed, "skipped_paths": skipped},
        )
    return success_result({"removed_paths": removed, "skipped_paths": skipped})


def cleanup_workflow_resources(
    state: dict[str, Any],
    *,
    settings: Settings | None = None,
    extra_temp_paths: Iterable[str] = (),
) -> ToolResult:
    """Workflow 임시 리소스를 정리하며 최종 export 파일은 보호합니다."""

    config = settings or get_settings()
    cleanup_targets = [
        *state.get("input_file_paths", []),
        *state.get("input_image_paths", []),
        state.get("base_rfp_path"),
        state.get("base_requirement_json_path"),
        state.get("erd_file_path"),
        state.get("interface_file_path"),
        state.get("existing_output_path"),
        config.temp_dir,
        config.extract_image_dir,
        config.mermaid_dir,
        *extra_temp_paths,
    ]
    export_result = state.get("export_result") or {}
    protected_paths = [
        export_result.get("local_file_path"),
        export_result.get("docx_path"),
        export_result.get("pdf_path"),
        export_result.get("hwp_path"),
    ]
    return cleanup_paths(
        [str(path) for path in cleanup_targets if path],
        protected_paths=[str(path) for path in protected_paths if path],
        allowed_root=config.local_storage_root,
    )


def _is_protected(target: Path, protected_paths: set[Path]) -> bool:
    return any(
        target == protected or target in protected.parents or protected in target.parents
        for protected in protected_paths
    )
