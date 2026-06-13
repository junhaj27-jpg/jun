# ERD 및 DB 데이터 구조 설계 Agent의 실행 진입점입니다.

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from agents.data_structure_design.processors import (
    build_db_design,
    build_domain_groups,
    build_entity_candidates,
    build_erd_tables,
    build_relationships,
    filter_data_requirements,
    normalize_db_design,
    normalize_erd_tables,
)
from tools.llm.llm_client import LLMClient
from tools.llm.response_parser import parse_json_response
from tools.llm.send_api import send_parallel
from tools.result import ToolResult
from tools.search.search_router import search
from workflow.state import WorkflowState


class DataStructureDesignAgent:
    def __init__(
        self,
        *,
        llm_client: LLMClient | None = None,
        search_tool: Callable[..., ToolResult] = search,
    ) -> None:
        self.llm_client = llm_client
        self.search_tool = search_tool

    def execute(self, state: WorkflowState) -> dict[str, Any]:
        docs_cd = str(state.get("docs_cd", "")).upper()
        mode = str(state.get("udt_yn", "")).upper()
        document_merge = state.get("agent_outputs", {}).get("document_merge_agent", {})
        if docs_cd == "ERD" and mode == "N":
            output = self._create_erd(document_merge, state)
        elif docs_cd == "ERD" and mode == "Y":
            output = self._update_erd(document_merge, state)
        elif docs_cd == "DB" and mode == "N":
            output = self._create_db(document_merge, state)
        elif docs_cd == "DB" and mode == "Y":
            output = self._update_db(document_merge, state)
        else:
            output = self._failed("DATA_STRUCTURE_INVALID_MODE", f"지원하지 않는 실행 조건입니다: {docs_cd}/{mode}")
        return self._store(state, output)

    def _create_erd(self, document_merge: dict[str, Any], state: WorkflowState) -> dict[str, Any]:
        requirements = document_merge.get("integrated_requirement_json_list")
        if not isinstance(requirements, list) or not requirements:
            return self._failed("ERD_REQUIREMENT_MISSING", "integrated_requirement_json_list가 필요합니다.")
        selected = filter_data_requirements(requirements)
        if not selected:
            return self._failed("ERD_DATA_REQUIREMENT_MISSING", "데이터 구조 설계 대상 요구사항이 없습니다.")
        groups = build_domain_groups(selected)
        entities = build_entity_candidates(groups)
        tables = build_erd_tables(entities)
        warnings, rag_results = self._standard_search(tables, state)
        llm_analysis, llm_warnings = self._parallel_llm_analysis(groups, "도메인별 엔티티 후보와 데이터 구조 영향을 분석하세요.")
        warnings.extend(llm_warnings)
        return self._erd_success(state, tables, build_relationships(tables), warnings, {"domain_group_list": groups, "entity_candidate_list": entities, "rag_results": rag_results, "llm_analysis": llm_analysis})

    def _update_erd(self, document_merge: dict[str, Any], state: WorkflowState) -> dict[str, Any]:
        existing = document_merge.get("existing_output_raw_json")
        changes = document_merge.get("meeting_change_items")
        if not isinstance(existing, dict) or not existing:
            return self._failed("ERD_EXISTING_OUTPUT_MISSING", "existing_output_raw_json이 필요합니다.")
        if not isinstance(changes, list):
            return self._failed("ERD_MEETING_CHANGE_MISSING", "meeting_change_items가 필요합니다.")
        tables = normalize_erd_tables(_extract_tables(existing))
        llm_analysis, warnings = self._parallel_llm_analysis(changes, "회의록 변경사항의 ERD 엔티티, 컬럼, 관계 영향을 분석하세요.")
        tables = _apply_table_changes(tables, changes)
        return self._erd_success(state, tables, build_relationships(tables), warnings, {"meeting_change_items": changes, "llm_analysis": llm_analysis})

    def _create_db(self, document_merge: dict[str, Any], state: WorkflowState) -> dict[str, Any]:
        reference = document_merge.get("reference_erd_json_list")
        if not isinstance(reference, list) or not reference:
            return self._failed("DB_REFERENCE_ERD_MISSING", "reference_erd_json_list가 필요합니다.")
        tables = normalize_erd_tables(reference)
        llm_analysis, warnings = self._parallel_llm_analysis(tables, "ERD 테이블별 DB 명세, 데이터 타입, 제약조건, 인덱스를 분석하세요.")
        return self._db_success(state, build_db_design(tables), warnings, {"reference_erd_json_list": reference, "llm_analysis": llm_analysis})

    def _update_db(self, document_merge: dict[str, Any], state: WorkflowState) -> dict[str, Any]:
        artifacts = document_merge.get("integrated_artifact_json_list")
        if not isinstance(artifacts, list) or not artifacts:
            return self._failed("DB_ARTIFACT_MISSING", "integrated_artifact_json_list가 필요합니다.")
        llm_analysis, warnings = self._parallel_llm_analysis(artifacts, "기존 DB 설계서의 컬럼, 제약조건, 인덱스 변경사항을 검토하세요.")
        return self._db_success(
            state,
            normalize_db_design(_flatten_tables(artifacts)),
            warnings,
            {"source_artifacts": artifacts, "llm_analysis": llm_analysis},
        )

    def _parallel_llm_analysis(
        self,
        items: list[Any],
        instruction: str,
    ) -> tuple[list[Any], list[dict[str, Any]]]:
        if self.llm_client is None or not items:
            return [], []
        result = send_parallel(
            [
                {
                    "messages": [
                        {"role": "system", "content": instruction},
                        {"role": "user", "content": str(item)},
                    ]
                }
                for item in items
            ],
            client=self.llm_client,
        )
        if not result["success"]:
            return [], [{"code": "DATA_STRUCTURE_LLM_FAILED", "message": result["error"]["message"]}]
        analyses = []
        warnings = []
        for index, response in enumerate(result["data"]):
            parsed = parse_json_response(response["data"]) if response and response["success"] else None
            if parsed and parsed["success"]:
                analyses.append(parsed["data"])
            else:
                warnings.append({"code": "DATA_STRUCTURE_LLM_ITEM_FAILED", "message": f"LLM 분석 항목 {index + 1} 처리에 실패했습니다."})
        return analyses, warnings

    def _standard_search(
        self,
        tables: list[dict[str, Any]],
        state: WorkflowState,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        warnings = []
        results = []
        for table in tables:
            result = self.search_tool(
                f"{table['logical_name']} 공공데이터 컬럼 표준명 용어사전",
                search_targets="RAG",
                filters={"project_sn": state.get("project_sn"), "category": "data_standard"},
            )
            if result["success"]:
                results.append({"table_id": table["table_id"], "normalized_results": result["data"]["normalized_results"]})
            else:
                warnings.append({"code": "DATA_STANDARD_RAG_FAILED", "message": result["error"]["message"], "table_id": table["table_id"]})
        return warnings, results

    @staticmethod
    def _erd_success(state, tables, relationships, warnings, debug):
        output = {
            "status": "SUCCESS",
            "erd_entity_json": {"tables": tables, "relationships": relationships},
            "erd_mermaid_json": {"entities": [{"name": table["physical_name"], "columns": table["columns"]} for table in tables], "relationships": relationships},
            "warnings": warnings,
            "errors": [],
        }
        if bool(state.get("etc", {}).get("debug")):
            output["debug"] = debug
        return output

    @staticmethod
    def _db_success(state, design, warnings, debug):
        output = {"status": "SUCCESS", "db_design_json": design, "warnings": warnings, "errors": []}
        if bool(state.get("etc", {}).get("debug")):
            output["debug"] = debug
        return output

    @staticmethod
    def _store(state: WorkflowState, output: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("agent_outputs", {})["data_structure_design_agent"] = output
        return output

    @staticmethod
    def _failed(code: str, message: str) -> dict[str, Any]:
        return {"status": "FAILED", "failure_type": code, "warnings": [], "errors": [{"code": code, "message": message}]}


def _extract_tables(document: dict[str, Any]) -> list[Any]:
    for key in ("tables", "entities", "erd_entity_json_list"):
        if isinstance(document.get(key), list):
            return document[key]
    return []


def _flatten_tables(items: list[Any]) -> list[Any]:
    tables: list[Any] = []
    for item in items:
        if isinstance(item, dict):
            nested = _extract_tables(item)
            tables.extend(nested if nested else [item])
    return tables


def _apply_table_changes(tables: list[dict[str, Any]], changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    updated = deepcopy(tables)
    for change in changes:
        operation = str(change.get("change_type") or change.get("operation") or "").upper()
        item = change.get("item")
        if operation == "ADD" and isinstance(item, dict):
            updated.extend(normalize_erd_tables([item]))
    return normalize_erd_tables(updated)
