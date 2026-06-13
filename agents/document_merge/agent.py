# 기존 산출물과 회의록을 분석하고 통합하는 Agent의 실행 진입점입니다.

from collections.abc import Callable
from typing import Any

from agents.document_merge.processors import analyze_meetings, artifact_items, merge_items, parse_artifact
from tools.llm.llm_client import LLMClient
from tools.parser.image_extractor import extract_images
from tools.parser.rfp_rule_parser import parse_rfp_requirements
from tools.result import ToolResult
from tools.search.search_router import search
from workflow.state import WorkflowState


class DocumentMergeAgent:
    def __init__(
        self,
        *,
        llm_client: LLMClient | None = None,
        rfp_parser: Callable[[str], ToolResult] = parse_rfp_requirements,
        search_tool: Callable[..., ToolResult] = search,
    ) -> None:
        self.llm_client = llm_client
        self.rfp_parser = rfp_parser
        self.search_tool = search_tool

    def execute(self, state: WorkflowState) -> dict[str, Any]:
        docs_cd = str(state.get("docs_cd", "")).upper()
        udt_yn = str(state.get("udt_yn", "")).upper()
        try:
            if udt_yn == "Y":
                output = self._update_artifact(state, docs_cd)
            elif docs_cd == "SRS":
                output = self._create_srs(state)
            else:
                output = self._create_other(state, docs_cd)
        except Exception as exc:
            output = self._failed("DOCUMENT_MERGE_FAILED", str(exc))
        state.setdefault("agent_outputs", {})["document_merge_agent"] = output
        return output

    def _create_srs(self, state: WorkflowState) -> dict[str, Any]:
        base_rfp_path = state.get("base_rfp_path")
        if not base_rfp_path:
            return self._failed("SRS_RFP_MISSING", "base_rfp_path가 필요합니다.")
        parsed = self.rfp_parser(base_rfp_path)
        if not parsed["success"]:
            return self._tool_failed("SRS_RFP_PARSE_FAILED", parsed)
        requirements = list(parsed["data"].get("requirements", []))
        changes, warnings = self._meeting_changes(state)
        changes = self._enrich_changes_with_search(changes, warnings)
        return self._success(
            warnings=warnings,
            integrated_requirement_json_list=merge_items(requirements, changes),
        )

    def _create_other(self, state: WorkflowState, docs_cd: str) -> dict[str, Any]:
        requirement_path = state.get("base_requirement_json_path")
        if not requirement_path:
            return self._failed("BASE_REQUIREMENT_MISSING", "base_requirement_json_path가 필요합니다.")
        parsed = parse_artifact(requirement_path)
        if not parsed["success"]:
            return self._tool_failed("BASE_REQUIREMENT_PARSE_FAILED", parsed)
        changes, warnings = self._meeting_changes(state)
        changes = self._enrich_changes_with_search(changes, warnings)
        output = self._success(
            warnings=warnings,
            integrated_requirement_json_list=merge_items(artifact_items(parsed["data"]), changes),
        )
        if docs_cd == "DB":
            reference = self._parse_reference(state.get("erd_file_path"), "ERD")
            if not reference["success"]:
                return reference["output"]
            output["reference_erd_json_list"] = reference["items"]
        elif docs_cd == "TS":
            reference = self._parse_reference(state.get("interface_file_path"), "INTERFACE")
            if not reference["success"]:
                return reference["output"]
            output["reference_interface_json_list"] = reference["items"]
        return output

    def _update_artifact(self, state: WorkflowState, docs_cd: str) -> dict[str, Any]:
        existing_path = state.get("existing_output_path")
        meeting_paths = list(state.get("input_file_paths") or [])
        if not existing_path:
            return self._failed("EXISTING_OUTPUT_MISSING", "existing_output_path가 필요합니다.")
        if not meeting_paths:
            return self._failed("MEETING_FILE_MISSING", "수정 모드에는 회의록 파일이 필요합니다.")
        parsed = parse_artifact(existing_path)
        if not parsed["success"]:
            return self._tool_failed("EXISTING_OUTPUT_PARSE_FAILED", parsed)
        image_result = extract_images(existing_path)
        image_paths = image_result["data"]["image_paths"] if image_result["success"] else []
        changes, warnings = self._meeting_changes(state)
        changes = self._enrich_changes_with_search(changes, warnings)
        raw_json = parsed["data"].get("raw_json", parsed["data"])
        if docs_cd in {"ERD", "DB", "ARCH"}:
            return self._success(
                warnings=warnings,
                existing_output_raw_json=raw_json,
                meeting_change_items=changes,
                existing_output_image_paths=image_paths,
            )
        return self._success(
            warnings=warnings,
            integrated_artifact_json_list=merge_items(artifact_items(raw_json), changes),
            existing_output_image_paths=image_paths,
        )

    def _meeting_changes(self, state: WorkflowState) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        excluded_paths = {
            str(path)
            for path in (
                state.get("base_rfp_path"),
                state.get("base_requirement_json_path"),
                state.get("erd_file_path"),
                state.get("interface_file_path"),
                state.get("existing_output_path"),
            )
            if path
        }
        return analyze_meetings(
            [
                path
                for path in list(state.get("input_file_paths") or [])
                if str(path) not in excluded_paths
            ],
            llm_client=self.llm_client,
        )

    def _enrich_changes_with_search(
        self,
        changes: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        for change in changes:
            target = str(change.get("search_targets") or "NONE").upper()
            query = change.get("search_query")
            if target == "NONE" or not query:
                continue
            result = self.search_tool(str(query), search_targets=target)
            if result["success"]:
                change["search_results"] = result["data"]["normalized_results"]
            else:
                warnings.append({"code": "DOCUMENT_MERGE_SEARCH_FAILED", "message": result["error"]["message"]})
        return changes

    @staticmethod
    def _parse_reference(path: str | None, reference_type: str) -> dict[str, Any]:
        if not path:
            return {
                "success": False,
                "output": DocumentMergeAgent._failed(
                    f"REFERENCE_{reference_type}_MISSING",
                    f"{reference_type} 참조 파일 경로가 필요합니다.",
                ),
            }
        parsed = parse_artifact(path)
        if not parsed["success"]:
            return {
                "success": False,
                "output": DocumentMergeAgent._tool_failed(
                    f"REFERENCE_{reference_type}_PARSE_FAILED", parsed
                ),
            }
        return {"success": True, "items": artifact_items(parsed["data"])}

    @staticmethod
    def _success(*, warnings: list[dict[str, Any]], **values: Any) -> dict[str, Any]:
        return {"status": "SUCCESS", **values, "warnings": warnings, "errors": []}

    @staticmethod
    def _failed(code: str, message: str) -> dict[str, Any]:
        return {"status": "FAILED", "failure_type": code, "warnings": [], "errors": [{"code": code, "message": message}]}

    @staticmethod
    def _tool_failed(code: str, result: ToolResult) -> dict[str, Any]:
        return DocumentMergeAgent._failed(code, str(result["error"]["message"]))
