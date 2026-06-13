# 이미지 분석 Agent의 실행 진입점입니다.

from collections.abc import Callable
from typing import Any

from agents.image_analysis.processors import (
    analyze_images,
    build_description,
    match_creation_screens,
    match_update_screens,
)
from tools.llm.llm_client import LLMClient
from tools.result import ToolResult
from tools.search.search_router import search
from workflow.state import WorkflowState


class ImageAnalysisAgent:
    def __init__(
        self,
        *,
        llm_client: LLMClient | None = None,
        search_tool: Callable[..., ToolResult] = search,
    ) -> None:
        self.llm_client = llm_client
        self.search_tool = search_tool

    def execute(self, state: WorkflowState) -> dict[str, Any]:
        if str(state.get("docs_cd", "")).upper() != "INTERFACE":
            return self._store(state, self._failed("IMAGE_ANALYSIS_INVALID_DOCS_CD", "image_analysis_agent는 INTERFACE 산출물에서만 실행할 수 있습니다."))

        mode = str(state.get("udt_yn", "")).upper()
        document_merge = state.get("agent_outputs", {}).get("document_merge_agent", {})
        if mode == "N":
            requirements = document_merge.get("integrated_requirement_json_list")
            if not isinstance(requirements, list) or not requirements:
                return self._store(state, self._failed("INTERFACE_REQUIREMENT_MISSING", "integrated_requirement_json_list가 필요합니다."))
            image_paths = list(state.get("input_image_paths") or [])
            if not image_paths:
                return self._store(state, self._failed("INTERFACE_IMAGE_MISSING", "INTERFACE 신규 생성에는 이미지가 필요합니다."))
            analyses, warnings = analyze_images(image_paths, llm_client=self.llm_client)
            screens = match_creation_screens(requirements, analyses)
        elif mode == "Y":
            artifacts = document_merge.get("integrated_artifact_json_list")
            if not isinstance(artifacts, list) or not artifacts:
                return self._store(state, self._failed("NEED_SUPERVISOR_DECISION", "integrated_artifact_json_list가 필요합니다."))
            image_paths = list(
                dict.fromkeys(
                    [
                        *(document_merge.get("existing_output_image_paths") or []),
                        *(state.get("input_image_paths") or []),
                    ]
                )
            )
            if not image_paths:
                return self._store(state, self._failed("INTERFACE_IMAGE_MISSING", "기존 이미지와 신규 이미지가 모두 없습니다."))
            analyses, warnings = analyze_images(image_paths, llm_client=self.llm_client)
            screens = match_update_screens(artifacts, analyses)
        else:
            return self._store(state, self._failed("IMAGE_ANALYSIS_INVALID_MODE", f"허용되지 않은 udt_yn입니다: {mode}"))

        search_debug = []
        for screen in screens:
            ux_guides = self._search(
                f"{screen['screen_name']} UI UX 가이드",
                {"category": "ui_ux_guide", "screen_type": screen["screen_name"]},
                warnings,
            )
            interface_requirements = self._search(
                f"{screen['screen_name']} 인터페이스 요구사항",
                {
                    "project_sn": state.get("project_sn"),
                    "requirement_type": "인터페이스 요구사항",
                },
                warnings,
            )
            screen["description"] = build_description(
                screen,
                ux_guides=ux_guides,
                interface_requirements=interface_requirements,
            )
            search_debug.append(
                {
                    "screen_id": screen["screen_id"],
                    "ux_guides": ux_guides,
                    "interface_requirements": interface_requirements,
                }
            )

        output: dict[str, Any] = {
            "status": "SUCCESS",
            "interface_image_analysis_json_list": screens,
            "warnings": warnings,
            "errors": [],
        }
        if bool(state.get("etc", {}).get("debug")):
            output["debug"] = {
                "image_analysis_result_list": analyses,
                "rag_results": search_debug,
            }
        return self._store(state, output)

    def _search(
        self,
        query: str,
        filters: dict[str, Any],
        warnings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result = self.search_tool(query, search_targets="RAG", filters=filters)
        if result["success"]:
            return result["data"]["normalized_results"]
        warnings.append({"code": "IMAGE_ANALYSIS_RAG_FAILED", "message": result["error"]["message"], "query": query})
        return []

    @staticmethod
    def _store(state: WorkflowState, output: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("agent_outputs", {})["image_analysis_agent"] = output
        return output

    @staticmethod
    def _failed(code: str, message: str) -> dict[str, Any]:
        return {
            "status": "FAILED",
            "failure_type": code,
            "warnings": [],
            "errors": [{"code": code, "message": message}],
        }
