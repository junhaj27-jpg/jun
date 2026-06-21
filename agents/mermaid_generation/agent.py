# Mermaid 코드 및 이미지 생성 Agent의 실행 진입점입니다.

from collections.abc import Callable
from pathlib import Path
from typing import Any

from agents.mermaid_generation.architecture_builder import build_architecture_mermaid
from agents.mermaid_generation.erd_builder import build_erd_mermaid
from agents.mermaid_generation.erd_grouping import split_erd_structure
from tools.llm.llm_client import LLMClient
from tools.mermaid import llm_repair, render_mermaid, rule_repair, validate_mermaid
from tools.result import ToolResult
from workflow.state import WorkflowState


class MermaidGenerationAgent:
    def __init__(
        self,
        *,
        llm_client: LLMClient | None = None,
        renderer: Callable[..., ToolResult] = render_mermaid,
    ) -> None:
        self.llm_client = llm_client
        self.renderer = renderer

    def execute(self, state: WorkflowState) -> dict[str, Any]:
        docs_cd = str(state.get("docs_cd", "")).upper()
        if docs_cd == "ERD":
            structure = state.get("agent_outputs", {}).get("data_structure_design_agent", {}).get("erd_mermaid_json")
            if not _valid_erd_structure(structure):
                return self._store(state, self._failed("ERD_MERMAID_INPUT_INVALID", "erd_mermaid_json에 엔티티/테이블 구조가 필요합니다."))
            output = self._execute_erd(state, structure)
            return self._store(state, output)
        elif docs_cd == "ARCH":
            structure = state.get("agent_outputs", {}).get("architecture_analysis_agent", {}).get("architecture_structure_json")
            if not _valid_arch_structure(structure):
                return self._store(state, self._failed("ARCH_MERMAID_INPUT_INVALID", "architecture_structure_json에 컴포넌트 구조가 필요합니다."))
            code = build_architecture_mermaid(structure)
        else:
            return self._store(state, self._failed("MERMAID_INVALID_DOCS_CD", f"Mermaid 생성을 지원하지 않는 docs_cd입니다: {docs_cd}"))

        validation = validate_mermaid(code, docs_cd)
        if not validation["success"]:
            code = rule_repair(code)

        attempts: list[dict[str, Any]] = []
        for attempt in range(3):
            result = self.renderer(code, file_stem=f"{docs_cd.lower()}_diagram")
            attempts.append({"attempt": attempt + 1, "success": result["success"], "error": result["error"]})
            if result["success"]:
                renderer_warnings = list(result["data"].get("warnings", []))
                if attempt != 0:
                    renderer_warnings.append(
                        {
                            "code": "MERMAID_REPAIRED",
                            "message": f"{attempt}회 보정 후 렌더링에 성공했습니다.",
                        }
                    )
                output = {
                    "status": "SUCCESS",
                    "mermaid_code": code,
                    "mermaid_file_path": result["data"]["mermaid_file_path"],
                    "mermaid_image_path": result["data"]["mermaid_image_path"],
                    "warnings": renderer_warnings,
                    "errors": [],
                }
                if bool(state.get("etc", {}).get("debug")):
                    output["debug"] = {"render_attempts": attempts}
                return self._store(state, output)
            error_message = str(result["error"]["message"])
            if attempt == 0:
                code = rule_repair(code)
            elif attempt == 1:
                repaired = llm_repair(code, error_message, self.llm_client)
                if repaired:
                    code = repaired

        output = {
            "status": "FAILED",
            "failure_type": f"{docs_cd}_MERMAID_RENDER_FAILED",
            "mermaid_code": code,
            "mermaid_file_path": _last_path(attempts),
            "mermaid_image_path": "",
            "warnings": [],
            "errors": [{"code": f"{docs_cd}_MERMAID_RENDER_FAILED", "message": "Mermaid 렌더링이 3회 모두 실패했습니다."}],
        }
        if bool(state.get("etc", {}).get("debug")):
            output["debug"] = {"render_attempts": attempts}
        return self._store(state, output)

    def _execute_erd(self, state: WorkflowState, structure: dict[str, Any]) -> dict[str, Any]:
        groups = split_erd_structure(structure)
        if not groups:
            return self._failed("ERD_MERMAID_INPUT_INVALID", "ERD 그룹을 생성할 수 없습니다.")
        coverage_result = _coverage_result(structure, groups)
        if coverage_result["missing_table_count"]:
            return self._failed(
                "ERD_MERMAID_COVERAGE_MISSING",
                f"ERD 그룹에서 누락된 엔티티가 있습니다: {coverage_result['missing_tables']}",
            )

        mermaid_codes: list[str] = []
        mermaid_file_paths: list[str] = []
        mermaid_image_paths: list[str] = []
        warnings: list[dict[str, Any]] = []
        debug_groups: list[dict[str, Any]] = []
        for index, group in enumerate(groups, start=1):
            group_type = str(group.get("group_type") or "detail")
            code = build_erd_mermaid(
                group,
                core_columns_only=True,
                max_columns=4 if group_type == "orphan" else 6,
            )
            prefix = "erd_orphan" if group_type == "orphan" else "erd_group"
            file_stem = f"{prefix}_{_group_file_index(group, index)}"
            diagram_type = "ERD"
            render_result = self._render_with_repair(
                code,
                diagram_type,
                file_stem,
                state,
                render_options=_erd_render_options(group_type),
            )
            debug_groups.append(
                {
                    "group_id": group["group_id"],
                    "group_name": group["group_name"],
                    "table_names": group["table_names"],
                    "render_attempts": render_result["attempts"],
                }
            )
            if not render_result["success"]:
                output = {
                    "status": "FAILED",
                    "failure_type": "ERD_MERMAID_RENDER_FAILED",
                    "mermaid_code": code,
                    "mermaid_file_path": render_result["mermaid_file_path"],
                    "mermaid_image_path": "",
                    "mermaid_codes": mermaid_codes + [code],
                    "mermaid_file_paths": mermaid_file_paths,
                    "mermaid_image_paths": mermaid_image_paths,
                    "mermaid_groups": groups,
                    "coverage_result": coverage_result,
                    "warnings": warnings,
                    "errors": [{"code": "ERD_MERMAID_RENDER_FAILED", "message": f"{group['group_id']} Mermaid 렌더링이 3회 모두 실패했습니다."}],
                }
                if bool(state.get("etc", {}).get("debug")):
                    output["debug"] = {"groups": debug_groups}
                return output
            trimmed_path = _trim_image_whitespace(render_result["mermaid_image_path"])
            render_result["mermaid_image_path"] = trimmed_path or render_result["mermaid_image_path"]
            mermaid_codes.append(render_result["code"])
            mermaid_file_paths.append(render_result["mermaid_file_path"])
            mermaid_image_paths.append(render_result["mermaid_image_path"])
            warnings.extend(render_result["warnings"])

        output = {
            "status": "SUCCESS",
            "mermaid_code": "\n\n".join(mermaid_codes),
            "mermaid_file_path": mermaid_file_paths[0] if mermaid_file_paths else "",
            "mermaid_image_path": mermaid_image_paths[0] if mermaid_image_paths else "",
            "mermaid_codes": mermaid_codes,
            "mermaid_file_paths": mermaid_file_paths,
            "mermaid_image_paths": mermaid_image_paths,
            "mermaid_groups": groups,
            "coverage_result": coverage_result,
            "warnings": warnings,
            "errors": [],
        }
        if bool(state.get("etc", {}).get("debug")):
            output["debug"] = {"groups": debug_groups}
        return output

    def _render_with_repair(
        self,
        code: str,
        docs_cd: str | None,
        file_stem: str,
        state: WorkflowState,
        render_options: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        validation = validate_mermaid(code, docs_cd)
        if not validation["success"]:
            code = rule_repair(code)

        attempts: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        for attempt in range(3):
            result = self.renderer(code, file_stem=file_stem, **(render_options or {}))
            attempts.append({"attempt": attempt + 1, "success": result["success"], "error": result["error"]})
            if result["success"]:
                warnings.extend(result["data"].get("warnings", []))
                if attempt != 0:
                    warnings.append(
                        {
                            "code": "MERMAID_REPAIRED",
                            "message": f"{attempt}회 보정 후 렌더링에 성공했습니다.",
                        }
                    )
                return {
                    "success": True,
                    "code": code,
                    "mermaid_file_path": result["data"]["mermaid_file_path"],
                    "mermaid_image_path": result["data"]["mermaid_image_path"],
                    "render_options": result["data"].get("render_options", {}),
                    "warnings": warnings,
                    "attempts": attempts,
                }
            error_message = str(result["error"]["message"])
            if attempt == 0:
                code = rule_repair(code)
            elif attempt == 1:
                repaired = llm_repair(code, error_message, self.llm_client)
                if repaired:
                    code = repaired

        return {
            "success": False,
            "code": code,
            "mermaid_file_path": _last_path(attempts),
            "mermaid_image_path": "",
            "render_options": {},
            "warnings": warnings,
            "attempts": attempts,
        }

    @staticmethod
    def _store(state: WorkflowState, output: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("agent_outputs", {})["mermaid_generation_agent"] = output
        return output

    @staticmethod
    def _failed(code: str, message: str) -> dict[str, Any]:
        return {
            "status": "FAILED",
            "failure_type": code,
            "mermaid_code": "",
            "mermaid_file_path": "",
            "mermaid_image_path": "",
            "warnings": [],
            "errors": [{"code": code, "message": message}],
        }


def _valid_erd_structure(structure: Any) -> bool:
    if not isinstance(structure, dict):
        return False
    entities = structure.get("entities") or structure.get("tables")
    if not isinstance(entities, list) or not entities:
        return False
    return any(
        isinstance(entity, dict)
        and (entity.get("name") or entity.get("physical_name") or entity.get("table_name"))
        and isinstance(entity.get("columns"), list)
        for entity in entities
    )


def _valid_arch_structure(structure: Any) -> bool:
    if not isinstance(structure, dict):
        return False
    components = structure.get("components")
    if not isinstance(components, list) or not components:
        return False
    return any(
        isinstance(component, dict)
        and (component.get("component_id") or component.get("id") or component.get("name"))
        for component in components
    )


def _last_path(attempts: list[dict[str, Any]]) -> str:
    for attempt in reversed(attempts):
        error = attempt.get("error") or {}
        details = error.get("details") or {}
        if details.get("mermaid_file_path"):
            return str(details["mermaid_file_path"])
    return ""


def _group_file_index(group: dict[str, Any], fallback_index: int) -> int:
    group_id = str(group.get("group_id") or "")
    suffix = group_id.rsplit("-", 1)[-1]
    if suffix.isdigit():
        return int(suffix)
    return fallback_index


def _coverage_result(structure: dict[str, Any], groups: list[dict[str, Any]]) -> dict[str, Any]:
    entities = structure.get("entities") or structure.get("tables") or []
    all_tables = {
        str(entity.get("table_name") or entity.get("physical_name") or entity.get("name"))
        for entity in entities
        if isinstance(entity, dict) and (entity.get("table_name") or entity.get("physical_name") or entity.get("name"))
    }
    rendered_tables = {
        str(name)
        for group in groups
        for name in group.get("table_names", [])
    }
    missing_tables = sorted(all_tables - rendered_tables)
    return {
        "all_table_count": len(all_tables),
        "rendered_table_count": len(rendered_tables),
        "missing_table_count": len(missing_tables),
        "missing_tables": missing_tables,
    }


def _erd_render_options(group_type: str) -> dict[str, int]:
    """DOCX 축소 삽입 전 고해상도 PNG를 만들기 위한 Mermaid 렌더 옵션입니다."""

    if group_type == "orphan":
        return {"render_width": 2200, "render_height": 1700, "render_scale": 3}
    return {"render_width": 2600, "render_height": 1800, "render_scale": 3}


def _trim_image_whitespace(image_path: str, *, padding: int = 32) -> str:
    """Mermaid 렌더링 결과의 바깥 흰 여백만 잘라 DOCX 삽입 가독성을 높입니다."""

    path = Path(str(image_path))
    if not path.is_file():
        return ""
    try:
        from PIL import Image, ImageChops

        with Image.open(path) as image:
            image.load()
            source = image.convert("RGB")
            background = Image.new("RGB", source.size, "WHITE")
            diff = ImageChops.difference(source, background)
            bbox = diff.getbbox()
            if not bbox:
                return str(path)
            left = max(0, bbox[0] - padding)
            top = max(0, bbox[1] - padding)
            right = min(source.width, bbox[2] + padding)
            bottom = min(source.height, bbox[3] + padding)
            if (left, top, right, bottom) == (0, 0, source.width, source.height):
                return str(path)
            source.crop((left, top, right, bottom)).save(path, format="PNG", optimize=True)
        return str(path)
    except Exception:
        return ""
