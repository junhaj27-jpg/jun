# 요구사항 생성 Agent의 실행 진입점입니다.

from collections.abc import Callable
from typing import Any

from agents.requirement_generation.processors import (
    build_final_requirement,
    build_integrated_text,
    build_rag_query,
    extract_constraints,
    filter_function_requirements,
    split_function_requirements,
)
from tools.llm.llm_client import LLMClient
from tools.result import ToolResult
from tools.search.search_router import search
from workflow.state import WorkflowState


class RequirementGenerationAgent:
    def __init__(
        self,
        *,
        llm_client: LLMClient | None = None,
        search_tool: Callable[..., ToolResult] = search,
    ) -> None:
        self.llm_client = llm_client
        self.search_tool = search_tool

    def execute(self, state: WorkflowState) -> dict[str, Any]:
        if str(state.get("docs_cd", "")).upper() != "SRS" or str(state.get("udt_yn", "")).upper() != "N":
            output = self._failed("REQUIREMENT_GENERATION_INVALID_MODE", "requirement_generation_agent는 SRS 신규 생성에서만 실행할 수 있습니다.")
            return self._store(state, output)

        integrated = state.get("agent_outputs", {}).get("document_merge_agent", {}).get(
            "integrated_requirement_json_list"
        )
        if not isinstance(integrated, list) or not integrated:
            return self._store(state, self._failed("INTEGRATED_REQUIREMENT_MISSING", "integrated_requirement_json_list가 없거나 비어 있습니다."))

        functional = filter_function_requirements(integrated)
        if not functional:
            return self._store(state, self._failed("FUNCTION_REQUIREMENT_MISSING", "기능 요구사항이 없습니다."))

        integrated_text = build_integrated_text(functional)
        split_items, warnings = split_function_requirements(
            functional,
            integrated_text,
            llm_client=self.llm_client,
        )
        search_debug: list[dict[str, Any]] = []
        final_items: list[dict[str, Any]] = []
        for split_item in split_items:
            query = build_rag_query(split_item)
            filters = {
                "project_sn": state.get("project_sn"),
                "requirement_source_id": split_item.get("source", []),
                "requirement_type": ["보안", "성능", "품질", "인터페이스", "데이터"],
            }
            search_result = self.search_tool(query, search_targets="RAG", filters=filters)
            normalized_results = (
                search_result["data"]["normalized_results"] if search_result["success"] else []
            )
            if not search_result["success"]:
                warnings.append({"code": "REQUIREMENT_RAG_SEARCH_FAILED", "message": search_result["error"]["message"], "query": query})
            constraints = extract_constraints(normalized_results)
            final_items.append(build_final_requirement(split_item, constraints))
            search_debug.append({"query": query, "filters": filters, "normalized_results": normalized_results})

        output: dict[str, Any] = {
            "status": "SUCCESS",
            "final_requirement_json_list": final_items,
            "warnings": warnings,
            "errors": [],
        }
        if bool(state.get("etc", {}).get("debug")):
            output["debug"] = {
                "functional_requirement_list": functional,
                "integrated_function_text": integrated_text,
                "split_function_requirement_list": split_items,
                "rag_searches": search_debug,
            }
        return self._store(state, output)

    @staticmethod
    def _store(state: WorkflowState, output: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("agent_outputs", {})["requirement_generation_agent"] = output
        return output

    @staticmethod
    def _failed(code: str, message: str) -> dict[str, Any]:
        return {
            "status": "FAILED",
            "failure_type": code,
            "warnings": [],
            "errors": [{"code": code, "message": message}],
        }
