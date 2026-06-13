# Mermaid 코드 및 이미지 생성 Agent의 실행 진입점입니다.

from collections.abc import Callable
from typing import Any

from agents.mermaid_generation.architecture_builder import build_architecture_mermaid
from agents.mermaid_generation.erd_builder import build_erd_mermaid
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
            code = build_erd_mermaid(structure)
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
                output = {
                    "status": "SUCCESS",
                    "mermaid_code": code,
                    "mermaid_file_path": result["data"]["mermaid_file_path"],
                    "mermaid_image_path": result["data"]["mermaid_image_path"],
                    "warnings": [] if attempt == 0 else [{"code": "MERMAID_REPAIRED", "message": f"{attempt}회 보정 후 렌더링에 성공했습니다."}],
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
    return isinstance(structure, dict) and bool(structure.get("entities") or structure.get("tables"))


def _valid_arch_structure(structure: Any) -> bool:
    return isinstance(structure, dict) and bool(structure.get("components"))


def _last_path(attempts: list[dict[str, Any]]) -> str:
    for attempt in reversed(attempts):
        error = attempt.get("error") or {}
        details = error.get("details") or {}
        if details.get("mermaid_file_path"):
            return str(details["mermaid_file_path"])
    return ""
