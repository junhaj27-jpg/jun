# ERD 및 DB 데이터 구조 설계 Agent의 실행 진입점입니다.

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import json
import re
from typing import Any

from agents.data_structure_design.processors import (
    apply_public_standard_results,
    build_db_design,
    build_domain_groups,
    build_entity_candidates,
    build_erd_tables,
    display_column_name,
    filter_data_requirements,
    format_type_and_length,
    normalize_db_design,
    normalize_erd_tables,
)
from config.settings import get_settings
from tools.llm.llm_client import LLMClient
from tools.llm.response_parser import parse_json_response
from tools.llm.send_api import send_parallel
from tools.result import ToolResult
from tools.search.search_router import search
from workflow.state import WorkflowState
from agents.data_structure_design.processors.column_standardizer import table_name
from agents.data_structure_design.pipeline import build_erd_from_requirements
from agents.data_structure_design.pipeline.metadata_enricher import enrich_table_metadata
from agents.data_structure_design.pipeline.relationship_inferer import infer_relationships
from agents.data_structure_design.pipeline.validator import validate_erd
from agents.data_structure_design.meeting_erd_requirements import (
    apply_meeting_erd_requirements,
    evaluate_meeting_erd_requirements,
    extract_meeting_erd_requirements,
)
from agents.document_merge.processors.artifact_parser import artifact_items


class DataStructureDesignAgent:
    def __init__(
        self,
        *,
        llm_client: LLMClient | None = None,
        search_tool: Callable[..., ToolResult] = search,
        max_parallel_workers: int = 4,
    ) -> None:
        self.llm_client = llm_client
        self.search_tool = search_tool
        self.max_parallel_workers = max(1, max_parallel_workers)

    def execute(self, state: WorkflowState) -> dict[str, Any]:
        repair_instruction = state.get("current_repair_instruction")
        if (
            isinstance(repair_instruction, dict)
            and repair_instruction.get("target_agent") == "data_structure_design_agent"
        ):
            return self._store(state, self._repair_erd_output(state, repair_instruction))
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
        selected = filter_data_requirements(requirements) or requirements
        pipeline_result = build_erd_from_requirements(selected)
        warnings: list[dict[str, Any]] = []

        domain_groups: list[dict[str, Any]] = []
        entity_candidates: list[dict[str, Any]] = []
        llm_tables: list[dict[str, Any]] = []
        if self.llm_client is not None:
            domain_groups, stage_warnings = self._build_domain_groups(selected)
            warnings.extend(stage_warnings)
            entity_candidates, stage_warnings = self._build_entity_candidates(domain_groups)
            warnings.extend(stage_warnings)
            llm_tables, stage_warnings = self._build_table_candidates(entity_candidates)
            warnings.extend(stage_warnings)

        # Rule 결과는 안전망으로 유지하고 LLM이 도출한 신규 업무 엔티티를 병합합니다.
        tables = _merge_rule_and_llm_tables(
            pipeline_result["erd_schema"].get("tables", []),
            llm_tables,
        )
        search_warnings, rag_results = self._standard_search(tables, state)
        warnings.extend(search_warnings)
        column_standard_warnings, column_standard_results = self._column_standard_search(tables, state)
        rag_results = _merge_rag_results(rag_results, column_standard_results)
        tables, stage_warnings = self._build_column_candidates(tables, rag_results)
        warnings.extend([*column_standard_warnings, *stage_warnings])
        tables = apply_public_standard_results(tables, column_standard_results)
        relationships, stage_warnings = self._build_relationships(tables)
        warnings.extend(stage_warnings)
        erd_entity_json, stage_warnings = self._build_final_erd_json(tables, relationships)
        warnings.extend(stage_warnings)
        erd_entity_json = _ensure_erd_contract(erd_entity_json)
        erd_mermaid_json, stage_warnings = self._build_erd_mermaid_json(erd_entity_json)
        warnings.extend(stage_warnings)
        validation_result = validate_erd(
            erd_entity_json.get("tables", []),
            erd_entity_json.get("relationships", []),
        )
        warnings.extend(validation_result.get("warnings", []))
        for error in validation_result.get("errors", []):
            warnings.append({"code": "ERD_PIPELINE_VALIDATION_WARNING", "message": str(error)})
        return self._erd_success(
            state,
            erd_entity_json,
            erd_mermaid_json,
            warnings,
            {
                "domain_info": pipeline_result["domain_info"],
                "data_structure_intermediate": pipeline_result["data_structure_intermediate"],
                "erd_schema": erd_entity_json,
                "erd_mermaid_json": erd_mermaid_json,
                "validation_result": validation_result,
                "domain_group_list": domain_groups,
                "entity_candidate_list": entity_candidates,
                "table_candidate_list": tables,
                "rag_results": rag_results,
                "standardized_tables": tables,
            },
        )

    def _update_erd(self, document_merge: dict[str, Any], state: WorkflowState) -> dict[str, Any]:
        existing = document_merge.get("existing_output_raw_json")
        changes = document_merge.get("meeting_change_items")
        if not isinstance(existing, dict) or not existing:
            return self._failed("ERD_EXISTING_OUTPUT_MISSING", "existing_output_raw_json이 필요합니다.")
        if not isinstance(changes, list):
            return self._failed("ERD_MEETING_CHANGE_MISSING", "meeting_change_items가 필요합니다.")
        existing_analysis = self._llm_dict("기존 ERD 구조를 분석하세요.", {"existing_output_raw_json": existing}, "ERD_EXISTING_ANALYSIS_LLM_FAILED")
        tables = normalize_erd_tables(_extract_tables(existing_analysis or existing))
        llm_analysis, warnings = self._parallel_llm_analysis(changes, "회의록 변경사항의 ERD 엔티티, 컬럼, 관계 영향을 분석하세요.")
        tables = _apply_table_changes(tables, changes)
        redesign = self._llm_dict(
            "기존 ERD와 회의록 변경사항을 기반으로 ERD를 재설계하고 JSON으로 반환하세요.",
            {"tables": tables, "meeting_change_items": changes, "llm_analysis": llm_analysis},
            "ERD_REDESIGN_LLM_FAILED",
        )
        tables = normalize_erd_tables(_extract_tables(redesign) or tables)
        relationships, relationship_warnings = self._build_relationships(tables)
        meeting_requirements = extract_meeting_erd_requirements(changes)
        if meeting_requirements:
            tables, relationships, meeting_report = apply_meeting_erd_requirements(
                tables,
                relationships,
                meeting_requirements,
            )
        else:
            meeting_report = {
                "meeting_change_requirements": [],
                "added_tables": [],
                "added_columns": [],
                "added_relationships": [],
            }
        erd_entity_json, erd_warnings = self._build_final_erd_json(tables, relationships)
        erd_entity_json = _ensure_erd_contract(erd_entity_json)
        meeting_validation = evaluate_meeting_erd_requirements(
            erd_entity_json.get("tables", []),
            erd_entity_json.get("relationships", []),
            meeting_requirements,
        )
        erd_mermaid_json, mermaid_warnings = self._build_erd_mermaid_json(erd_entity_json)
        warnings.extend([*relationship_warnings, *erd_warnings, *mermaid_warnings])
        return self._erd_success(
            state,
            erd_entity_json,
            erd_mermaid_json,
            warnings,
            {
                "meeting_change_items": changes,
                "llm_analysis": llm_analysis,
                "meeting_change_requirements": meeting_requirements,
                "meeting_change_reflection": meeting_validation,
                "meeting_change_apply_report": meeting_report,
            },
        )

    def _create_db(self, document_merge: dict[str, Any], state: WorkflowState) -> dict[str, Any]:
        reference = document_merge.get("reference_erd_json_list")
        if not isinstance(reference, list) or not reference:
            return self._failed("DB_REFERENCE_ERD_MISSING", "reference_erd_json_list가 필요합니다.")
        tables = normalize_erd_tables(reference)
        search_warnings, project_results = self._standard_search(tables, state)
        column_standard_warnings, column_standard_results = [], []
        standardized_tables = deepcopy(tables)
        if state.get("project_sn") is not None:
            column_standard_warnings, column_standard_results = self._column_standard_search(tables, state)
            standardized_tables = _apply_db_standard_column_ids(
                deepcopy(tables), column_standard_results
            )
        rag_by_table = {
            str(item.get("table_id")): item.get("normalized_results", [])
            for item in _merge_rag_results(project_results, column_standard_results)
        }
        standardized_tables = [
            {**table, "rag_context": rag_by_table.get(str(table.get("table_id")), [])}
            for table in standardized_tables
        ]
        erd_analysis = self._llm_dict("ERD 구조를 분석하세요. 테이블, 컬럼, PK, FK, 관계를 JSON으로 반환하세요.", {"tables": standardized_tables}, "DB_ERD_ANALYSIS_LLM_FAILED")
        design, warnings = self._build_db_specifications(standardized_tables)
        final_design, final_warnings = self._finalize_db_design(design)
        warnings.extend([*search_warnings, *column_standard_warnings, *final_warnings])
        return self._db_success(
            state,
            final_design,
            warnings,
            {
                "reference_erd_json_list": reference,
                "standardized_tables": standardized_tables,
                "column_standard_results": column_standard_results,
                "llm_analysis": erd_analysis,
            },
        )

    def _update_db(self, document_merge: dict[str, Any], state: WorkflowState) -> dict[str, Any]:
        artifacts = document_merge.get("integrated_artifact_json_list")
        existing_raw = document_merge.get("existing_output_raw_json")
        changes = document_merge.get("meeting_change_items")
        existing_db_tables = _extract_db_design_tables(existing_raw)
        if not isinstance(artifacts, list) or not artifacts:
            artifacts = existing_db_tables or (artifact_items(existing_raw) if isinstance(existing_raw, dict) else [])
        if not isinstance(artifacts, list) or not artifacts:
            return self._failed("DB_ARTIFACT_MISSING", "기존 DB 설계서 raw_json 또는 integrated_artifact_json_list가 필요합니다.")
        existing_analysis = self._llm_dict(
            "기존 DB 설계서 구조를 분석하세요.",
            {
                "integrated_artifact_json_list": artifacts,
                "existing_output_raw_json": existing_raw,
                "meeting_change_items": changes if isinstance(changes, list) else [],
            },
            "DB_EXISTING_ANALYSIS_LLM_FAILED",
        )
        llm_analysis, warnings = self._parallel_llm_analysis(
            artifacts,
            "기존 DB 설계서의 컬럼, 제약조건, 인덱스 변경사항과 회의록 반영 여부를 검토하세요.",
        )
        analyzed_tables = _extract_tables(existing_analysis) if existing_analysis else []
        if existing_db_tables:
            design = _normalize_existing_db_design(existing_db_tables)
        elif _looks_like_db_design_table_list(analyzed_tables):
            design = _normalize_existing_db_design(analyzed_tables)
        else:
            design = normalize_db_design(analyzed_tables or _flatten_tables(artifacts))
        final_design, final_warnings = self._finalize_db_design(design)
        warnings.extend(final_warnings)
        return self._db_success(
            state,
            final_design,
            warnings,
            {
                "source_artifacts": artifacts,
                "existing_output_raw_json": existing_raw,
                "meeting_change_items": changes if isinstance(changes, list) else [],
                "llm_analysis": llm_analysis,
            },
        )

    def _build_domain_groups(
        self,
        requirements: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        fallback = build_domain_groups(requirements)
        generated, warnings = self._parallel_llm_list(
            requirements,
            (
                "너는 SI 프로젝트 데이터 모델러입니다. 요구사항 그룹 분석을 수행해 시스템 전체 관점의 업무 도메인으로 묶으세요. "
                "기능 하나마다 도메인을 만들지 말고 사용자/권한, 기준정보/상세정보, 거래/이력, 문서/파일, "
                "연계/배치, 공통코드처럼 공유 데이터가 생기는 업무 단위로 통합하세요. 특정 산업 예시는 입력에 있을 때만 적용하세요. "
                "JSON으로 domain_group 또는 domain_group_list만 반환하세요."
            ),
            "domain_group",
            "domain_group_list",
            "ERD_DOMAIN_GROUP_LLM_FAILED",
        )
        return _normalize_domain_groups(generated or fallback), warnings

    def _build_entity_candidates(
        self,
        groups: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        fallback = build_entity_candidates(groups)
        generated, warnings = self._parallel_llm_list(
            groups,
            (
                "너는 통합 ERD 설계자입니다. 도메인별로 저장/관리 대상이 되는 핵심 엔티티 후보를 추출하세요. "
                "화면명이나 기능명을 그대로 엔티티로 만들지 말고, 중복/유사 개념은 하나로 병합하세요. "
                "각 엔티티는 entity_id(ENT-001 형식), logical_name, description(80자 이내 요약), "
                "source_requirement_ids를 포함하세요. JSON으로 entity 또는 entity_candidate_list만 반환하세요."
            ),
            "entity",
            "entity_candidate_list",
            "ERD_ENTITY_LLM_FAILED",
        )
        return _normalize_entities(generated or fallback), warnings

    def _build_table_candidates(
        self,
        entities: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        fallback = build_erd_tables(entities)
        generated, warnings = self._parallel_llm_list(
            entities,
            (
                "너는 공공 SI 프로젝트 DB 모델러입니다. 엔티티별 테이블 후보를 설계하세요. "
                "물리 테이블명은 소문자 snake_case이며 tbl_ 접두사를 사용하세요. "
                "entity_id는 ENT-001 형식으로 유지하고 description은 '{논리명} 정보를 관리하는 엔티티입니다.'처럼 "
                "문서에 들어갈 한 줄 설명만 작성하세요. 근거, 목록, 특수기호, 줄바꿈, 요구사항 나열은 금지합니다. "
                "각 테이블은 최소 6개 이상의 업무 컬럼을 가져야 하며, PK, 명칭/내용, 상태코드, 사용여부, 등록/수정일시 같은 "
                "공통 컬럼과 요구사항에서 도출한 핵심 업무 컬럼을 포함하세요. "
                "JSON으로 table 또는 table_candidate_list만 반환하세요."
            ),
            "table",
            "table_candidate_list",
            "ERD_TABLE_LLM_FAILED",
        )
        return normalize_erd_tables(generated or fallback), warnings

    def _build_column_candidates(
        self,
        tables: list[dict[str, Any]],
        rag_results: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        rag_by_table = {item["table_id"]: item.get("normalized_results", []) for item in rag_results}
        generated, warnings = self._parallel_llm_list(
            [
                {
                    "table": table,
                    "rag_results": rag_by_table.get(table["table_id"], []),
                    "instruction": (
                        "프로젝트 비기능/데이터 요구사항 RAG 결과와 공공데이터 표준, 컬럼 표준명, 용어사전을 반영해 컬럼 후보를 설계하세요. "
                        "컬럼은 6~20개 수준으로 설계하고, 한글 논리명/영문 물리명/데이터 타입/길이/PK/FK/NULL/설명을 포함하세요. "
                        "constraints에는 해당 컬럼에 직접 적용되는 보안/개인정보/보관/성능/입력값 제약만 넣으세요. "
                        "컬럼 설명이나 업무 의미는 description에만 쓰고, 제약 근거가 없으면 constraints는 빈 배열로 두세요."
                    ),
                }
                for table in tables
            ],
            (
                "테이블별 컬럼 후보를 설계하세요. 기능 요구사항의 입력값, 상태값, 이력, 파일, 권한, 검색 조건, "
                "연계 식별자를 컬럼으로 반영하고 2개짜리 축약 테이블을 만들지 마세요. "
                "제약조건은 project_sn 기준 RAG 결과에 근거가 있을 때만 컬럼 constraints에 작성하세요. "
                "JSON으로 table 또는 table_candidate_list를 반환하세요."
            ),
            "table",
            "table_candidate_list",
            "ERD_COLUMN_LLM_FAILED",
        )
        if not generated:
            return tables, warnings
        by_physical = {table["physical_name"]: table for table in tables}
        updated = []
        for item in generated:
            if not isinstance(item, dict):
                continue
            table = item.get("table") if isinstance(item.get("table"), dict) else item
            physical_name = str(table.get("physical_name") or table.get("table_name") or "")
            base = dict(by_physical.get(physical_name) or {})
            if item.get("column_candidate_list") and not table.get("columns"):
                table = {**table, "columns": item["column_candidate_list"]}
            base.update(table)
            updated.append(base)
        return normalize_erd_tables(updated or tables), warnings

    def _build_relationships(
        self,
        tables: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        fallback = infer_relationships(
            [
                {
                    **table,
                    "table_name": table.get("table_name") or table.get("physical_name"),
                    "columns": [
                        {
                            **column,
                            "column_name": column.get("column_name") or column.get("physical_name"),
                        }
                        for column in table.get("columns", [])
                        if isinstance(column, dict)
                    ],
                }
                for table in tables
                if isinstance(table, dict)
            ]
        )
        value = self._llm_dict(
            (
                "테이블 목록을 기준으로 PK/FK 관계를 설계하세요. 단순히 첫 번째 테이블을 모든 테이블의 부모로 만들지 말고 "
                "마스터-상세, 원본-이력, 업무객체-파일, 사용자-권한처럼 입력으로 설명 가능한 관계만 생성하세요. "
                "JSON으로 relationship_list 또는 relationships를 반환하세요."
            ),
            {"tables": tables, "fallback_relationships": fallback},
            "ERD_RELATION_LLM_FAILED",
        )
        relationships = value.get("relationship_list") or value.get("relationships") if isinstance(value, dict) else None
        return relationships if isinstance(relationships, list) and relationships else fallback, []

    def _build_final_erd_json(
        self,
        tables: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        fallback = {"tables": tables, "relationships": relationships}
        value = self._llm_dict(
            (
                "전체 데이터 구조를 병합하여 ERD JSON을 생성하세요. "
                "테이블/컬럼 물리명은 소문자 snake_case, entity_id는 ENT-001 형식, table_id는 TABLE-001 형식을 유지하세요. "
                "description/table_description은 DOCX 엔티티 설명 칸에 들어갈 80자 이내 요약문이어야 합니다. "
                "엔티티당 컬럼은 최소 6개 이상을 유지하고, 중복 테이블은 병합하세요. JSON 객체만 반환하세요."
            ),
            fallback,
            "ERD_FINAL_JSON_LLM_FAILED",
        )
        if isinstance(value, dict):
            tables_value = _extract_tables(value)
            relationships_value = value.get("relationships") or value.get("relationship_list")
            if tables_value:
                normalized_tables = normalize_erd_tables(tables_value)
                normalized_relationships = _normalize_relationship_names(
                    relationships_value if isinstance(relationships_value, list) else relationships,
                    normalized_tables,
                )
                normalized_tables = enrich_table_metadata(normalized_tables, normalized_relationships)
                return {
                    "tables": normalized_tables,
                    "relationships": normalized_relationships,
                }, []
        fallback_tables = normalize_erd_tables(fallback["tables"])
        fallback_relationships = _normalize_relationship_names(fallback["relationships"], fallback_tables)
        fallback_tables = enrich_table_metadata(fallback_tables, fallback_relationships)
        return {
            "tables": fallback_tables,
            "relationships": fallback_relationships,
        }, []

    def _build_erd_mermaid_json(
        self,
        erd_entity_json: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        fallback = {
            "entities": [
                _mermaid_entity_from_table(table)
                for table in erd_entity_json.get("tables", [])
            ],
            "relationships": erd_entity_json.get("relationships", []),
        }
        # Mermaid 입력은 완성된 ERD JSON의 논리 모델을 그대로 투영합니다.
        # 별도 LLM 변환을 허용하면 검증을 통과한 이름/관계가 다시 바뀔 수 있습니다.
        return fallback, []

    def _repair_erd_output(
        self,
        state: WorkflowState,
        instruction: dict[str, Any],
    ) -> dict[str, Any]:
        if str(state.get("docs_cd", "")).upper() != "ERD":
            return self._failed("REPAIR_DOCS_CD_INVALID", "현재 제한 수정은 ERD 산출물만 지원합니다.")
        previous = state.get("agent_outputs", {}).get("data_structure_design_agent", {})
        current = previous.get("erd_entity_json") if isinstance(previous, dict) else None
        if not isinstance(current, dict) or not current.get("tables"):
            return self._failed("REPAIR_SOURCE_MISSING", "제한 수정할 기존 erd_entity_json이 없습니다.")

        target_ids = set(instruction.get("target_scope", {}).get("entity_ids") or [])
        scoped_tables = [
            table
            for table in current.get("tables", [])
            if isinstance(table, dict) and str(table.get("entity_id")) in target_ids
        ]
        if not scoped_tables:
            return self._failed("REPAIR_SCOPE_INVALID", "repair_instruction의 대상 엔티티를 찾을 수 없습니다.")

        prompt = (
            "너는 ERD 논리 모델 품질 수정자다. repair_instruction의 대상 엔티티만 수정한다. "
            "must_fix만 수행하고 must_preserve와 forbidden_changes를 반드시 지킨다. "
            "generic 이름(엔티티, 테이블, 데이터, 정보, 객체, 항목, 관리, 업무)은 금지한다. "
            "논리명은 entity_name/attribute_name, 물리명은 table_name/column_name으로 분리한다. "
            "응답은 {\"tables\": [수정된 대상 엔티티의 완전한 객체]} JSON 객체만 반환한다."
        )
        payload = {
            "repair_instruction": instruction,
            "target_tables": scoped_tables,
        }
        candidate = self._repair_llm_dict(prompt, payload)
        candidate_tables = _extract_tables(candidate)
        if not candidate_tables:
            return self._repair_failed(
                previous,
                "ERD_REPAIR_LLM_FAILED",
                "LLM이 유효한 제한 수정 ERD JSON을 반환하지 않았습니다.",
            )

        repaired, error = _merge_scoped_erd_repair(current, candidate_tables, instruction)
        if error:
            return self._repair_failed(previous, "ERD_REPAIR_CONSTRAINT_VIOLATION", error)
        mermaid_json = {
            "entities": [_mermaid_entity_from_table(table) for table in repaired.get("tables", [])],
            "relationships": repaired.get("relationships", []),
        }
        return self._erd_success(
            state,
            repaired,
            mermaid_json,
            [],
            {"repair_instruction": instruction, "repair_candidate": candidate},
        )

    def _repair_llm_dict(self, instruction: str, payload: Any) -> dict[str, Any]:
        client = self.llm_client or LLMClient()
        result = client.chat(
            [
                {"role": "system", "content": instruction},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.0,
        )
        if not result["success"]:
            return {}
        parsed = parse_json_response(result["data"])
        return parsed["data"] if parsed["success"] and isinstance(parsed["data"], dict) else {}

    def _build_db_specifications(
        self,
        tables: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        fallback = build_db_design(tables)
        generated, warnings = self._parallel_llm_list(
            tables,
            "테이블별 DB 명세를 생성하세요. 테이블 설명, 컬럼 설명, 데이터 타입, 제약조건, Default, 인덱스를 JSON으로 반환하세요.",
            "table_specification",
            "table_specification_json",
            "DB_TABLE_SPEC_LLM_FAILED",
        )
        if not generated:
            return fallback, warnings
        generated_design = {
            "tables": [_normalize_db_table(item, index) for index, item in enumerate(generated)]
        }
        return _merge_db_design(fallback, generated_design), warnings

    def _finalize_db_design(
        self,
        design: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        value = self._llm_dict("DB 설계서를 재정리하고 JSON으로 db_design_json을 반환하세요.", design, "DB_FINAL_JSON_LLM_FAILED")
        if isinstance(value, dict):
            candidate = value.get("db_design_json") or value
            if isinstance(candidate, dict) and isinstance(candidate.get("tables"), list):
                normalized_candidate = {
                    **candidate,
                    "tables": [
                        _normalize_db_table(item, index)
                        for index, item in enumerate(candidate["tables"])
                    ],
                }
                return _merge_db_design(design, normalized_candidate), []
        return design, []

    def _parallel_llm_list(
        self,
        items: list[Any],
        instruction: str,
        item_key: str,
        list_key: str,
        warning_code: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if self.llm_client is None or not items:
            return [], []
        result = send_parallel(
            [
                {"messages": [{"role": "system", "content": instruction}, {"role": "user", "content": str(item)}]}
                for item in items
            ],
            client=self.llm_client,
            max_workers=self.max_parallel_workers,
        )
        if not result["success"]:
            return [], [{"code": warning_code, "message": result["error"]["message"]}]
        output: list[dict[str, Any]] = []
        warnings = []
        for index, response in enumerate(result["data"]):
            parsed = parse_json_response(response["data"]) if response and response["success"] else None
            value = parsed["data"] if parsed and parsed["success"] else None
            extracted = _extract_llm_items(value, item_key, list_key)
            if extracted:
                output.extend(extracted)
            else:
                warnings.append({"code": warning_code, "message": f"LLM 항목 {index + 1} 결과를 기본값으로 대체합니다."})
        return output, warnings

    def _llm_dict(
        self,
        instruction: str,
        payload: Any,
        warning_code: str,
    ) -> dict[str, Any]:
        if self.llm_client is None:
            return {}
        result = self.llm_client.chat(
            [
                {"role": "system", "content": instruction},
                {"role": "user", "content": str(payload)},
            ]
        )
        if not result["success"]:
            return {}
        parsed = parse_json_response(result["data"])
        return parsed["data"] if parsed["success"] and isinstance(parsed["data"], dict) else {}

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
            max_workers=self.max_parallel_workers,
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
        results_by_table: dict[str, list[dict[str, Any]]] = {}
        settings = get_settings()
        with ThreadPoolExecutor(max_workers=self.max_parallel_workers) as executor:
            future_map = {}
            for table in tables:
                future_map[
                    executor.submit(
                        self.search_tool,
                        f"{table['logical_name']} 공공데이터 컬럼 표준명 용어사전",
                        search_targets="RAG",
                        filters={
                            "domain": "public_data",
                            "doc_type": ["standard_term", "standard_word", "standard_domain", "db_standard_manual"],
                        },
                        collection=settings.alpled_reference_collection,
                    )
                ] = table
                future_map[
                    executor.submit(
                        self.search_tool,
                        f"{table['logical_name']} 데이터 개인정보 보안 보관 성능 제약조건",
                        search_targets="RAG",
                        filters={
                            "project_sn": state.get("project_sn"),
                            "doc_type": "project_non_functional_requirement",
                            "domain": "requirements",
                            "chunk_type": "project_requirement_source",
                        },
                        collection=settings.alpled_reference_collection,
                    )
                ] = table
            for future in as_completed(future_map):
                table = future_map[future]
                try:
                    result = future.result()
                except Exception as exc:
                    warnings.append({"code": "DATA_STANDARD_RAG_FAILED", "message": str(exc), "table_id": table["table_id"]})
                    continue
                if result["success"]:
                    results_by_table.setdefault(table["table_id"], []).extend(
                        result["data"]["normalized_results"]
                    )
                else:
                    warnings.append({"code": "DATA_STANDARD_RAG_FAILED", "message": result["error"]["message"], "table_id": table["table_id"]})
        results = [
            {"table_id": table_id, "normalized_results": _dedupe_results(items)}
            for table_id, items in results_by_table.items()
        ]
        return warnings, results

    def _column_standard_search(
        self,
        tables: list[dict[str, Any]],
        state: WorkflowState,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        warnings = []
        results_by_table: dict[str, list[dict[str, Any]]] = {}
        settings = get_settings()
        filters = {
            "domain": "public_data",
            "doc_type": ["standard_term", "standard_word", "standard_domain"],
        }
        with ThreadPoolExecutor(max_workers=self.max_parallel_workers) as executor:
            future_map = {}
            for table in tables:
                for column in table.get("columns", []):
                    if not isinstance(column, dict):
                        continue
                    query = (
                        f"{column.get('logical_name') or column.get('physical_name')} "
                        "공통표준용어 공통표준단어 공통표준도메인 영문약어 데이터타입 저장 형식 길이"
                    )
                    future_map[
                        executor.submit(
                            self.search_tool,
                            query,
                            search_targets="RAG",
                            filters=filters,
                            top_k=5,
                            collection=settings.alpled_reference_collection,
                        )
                    ] = table
            for future in as_completed(future_map):
                table = future_map[future]
                try:
                    result = future.result()
                except Exception as exc:
                    warnings.append({"code": "COLUMN_STANDARD_RAG_FAILED", "message": str(exc), "table_id": table["table_id"]})
                    continue
                if result["success"]:
                    results_by_table.setdefault(table["table_id"], []).extend(result["data"]["normalized_results"])
                else:
                    warnings.append({"code": "COLUMN_STANDARD_RAG_FAILED", "message": result["error"]["message"], "table_id": table["table_id"]})
        return warnings, [
            {"table_id": table_id, "normalized_results": _dedupe_results(items)}
            for table_id, items in results_by_table.items()
        ]

    @staticmethod
    def _erd_success(state, erd_entity_json, erd_mermaid_json, warnings, debug):
        output = {
            "status": "SUCCESS",
            "erd_entity_json": erd_entity_json,
            "erd_mermaid_json": erd_mermaid_json,
            "warnings": warnings,
            "errors": [],
        }
        for key in ("meeting_change_requirements", "meeting_change_reflection", "meeting_change_apply_report"):
            if key in debug:
                output[key] = debug[key]
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

    @staticmethod
    def _repair_failed(previous: dict[str, Any], code: str, message: str) -> dict[str, Any]:
        """재시도 시 기존 ERD 원본을 잃지 않도록 실패 결과에도 보존합니다."""

        return {
            **DataStructureDesignAgent._failed(code, message),
            "erd_entity_json": previous.get("erd_entity_json"),
            "erd_mermaid_json": previous.get("erd_mermaid_json"),
        }


def _ensure_erd_contract(document: dict[str, Any]) -> dict[str, Any]:
    """ERD JSON의 논리/물리 alias를 명시하되 의미를 새로 추론하지 않습니다."""

    result = deepcopy(document)
    tables = result.get("tables") if isinstance(result.get("tables"), list) else []
    for table in tables:
        if not isinstance(table, dict):
            continue
        entity_name = str(table.get("entity_name") or table.get("logical_name") or "").strip()
        table_name_value = str(table.get("table_name") or table.get("physical_name") or "").strip()
        description = str(
            table.get("entity_description")
            or table.get("description")
            or table.get("table_description")
            or ""
        ).strip()
        table["entity_name"] = entity_name
        table["logical_name"] = entity_name
        table["table_name"] = table_name_value
        table["physical_name"] = table_name_value
        table["entity_description"] = description
        table["description"] = description
        table["table_description"] = description
        for column in table.get("columns", []):
            if not isinstance(column, dict):
                continue
            attribute_name = str(
                column.get("attribute_name")
                or column.get("logical_name")
                or column.get("column_logical_name")
                or ""
            ).strip()
            column_name = str(column.get("column_name") or column.get("physical_name") or "").strip()
            column["attribute_name"] = attribute_name
            column["logical_name"] = attribute_name
            column["column_name"] = column_name
            column["physical_name"] = column_name
    return result


def _merge_rule_and_llm_tables(
    rule_tables: list[dict[str, Any]],
    llm_tables: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """동일 논리 엔티티는 LLM 설계를 우선하고 Rule 초안은 안전망으로 남깁니다."""

    llm_keys = {_logical_table_key(table) for table in llm_tables if _logical_table_key(table)}
    retained_rules = [
        table for table in rule_tables if _logical_table_key(table) not in llm_keys
    ]
    return normalize_erd_tables([*retained_rules, *llm_tables])


def _apply_db_standard_column_ids(
    tables: list[dict[str, Any]],
    rag_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """참조 ERD 물리명은 보존하고 공공용어 약어는 DB 컬럼 ID에만 반영합니다."""

    standardized = apply_public_standard_results(deepcopy(tables), rag_results)
    standards_by_table = {
        str(table.get("table_id")): table for table in standardized if isinstance(table, dict)
    }
    for table in tables:
        standard_table = standards_by_table.get(str(table.get("table_id")), {})
        standard_columns = standard_table.get("columns") if isinstance(standard_table, dict) else []
        standard_by_logical = {
            str(column.get("logical_name")): column
            for column in standard_columns or []
            if isinstance(column, dict)
        }
        for column in table.get("columns", []):
            if not isinstance(column, dict):
                continue
            standard = standard_by_logical.get(str(column.get("logical_name")))
            if standard:
                column["standard_column_id"] = standard.get("physical_name")
                column["standard_source"] = standard.get("standard_source")
    return tables


def _logical_table_key(table: dict[str, Any]) -> str:
    value = str(
        table.get("entity_name")
        or table.get("logical_name")
        or table.get("table_korean_name")
        or ""
    )
    return re.sub(r"[\s_-]+", "", value).lower()


def _merge_scoped_erd_repair(
    current: dict[str, Any],
    candidates: list[dict[str, Any]],
    instruction: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    """LLM 결과에서 허용된 의미 필드만 반영하고 구조 필드는 강제로 보존합니다."""

    result = deepcopy(current)
    target_ids = set(instruction.get("target_scope", {}).get("entity_ids") or [])
    column_scopes = set(instruction.get("target_scope", {}).get("column_scopes") or [])
    failure_types = set(instruction.get("failure_types") or [instruction.get("failure_type")])
    candidate_by_id = {
        str(table.get("entity_id")): table
        for table in candidates
        if isinstance(table, dict) and table.get("entity_id")
    }
    unexpected = set(candidate_by_id) - target_ids
    if unexpected:
        return current, f"대상 범위 밖 엔티티가 응답에 포함되었습니다: {sorted(unexpected)}"

    repaired_ids: set[str] = set()
    for table in result.get("tables", []):
        if not isinstance(table, dict):
            continue
        entity_id = str(table.get("entity_id") or "")
        if entity_id not in target_ids:
            continue
        candidate = candidate_by_id.get(entity_id)
        if not candidate:
            return current, f"수정 대상 엔티티가 LLM 응답에 없습니다: {entity_id}"
        if _physical_table_name(candidate) != _physical_table_name(table):
            return current, f"보존 대상 물리 테이블명이 변경되었습니다: {entity_id}"
        repaired_ids.add(entity_id)

        if failure_types & {"ENTITY_GENERIC_NAME", "ENTITY_NAME_MISMATCH"}:
            name = str(candidate.get("entity_name") or candidate.get("logical_name") or "").strip()
            if _is_generic_repair_name(name):
                return current, f"유효한 entity_name을 생성하지 못했습니다: {entity_id}"
            table["entity_name"] = name
            table["logical_name"] = name

        if "ENTITY_DESCRIPTION_MISMATCH" in failure_types:
            description = str(
                candidate.get("entity_description")
                or candidate.get("description")
                or candidate.get("table_description")
                or ""
            ).strip()
            if not description:
                return current, f"유효한 entity_description을 생성하지 못했습니다: {entity_id}"
            table["entity_description"] = description
            table["description"] = description
            table["table_description"] = description

        if "ENTITY_ATTRIBUTE_MISMATCH" in failure_types:
            error = _merge_repaired_attributes(table, candidate, entity_id, column_scopes)
            if error:
                return current, error

    missing = target_ids - repaired_ids
    if missing:
        return current, f"ERD에서 수정 대상 엔티티를 찾지 못했습니다: {sorted(missing)}"
    return result, None


def _merge_repaired_attributes(
    table: dict[str, Any],
    candidate: dict[str, Any],
    entity_id: str,
    column_scopes: set[str],
) -> str | None:
    candidate_columns = candidate.get("columns") if isinstance(candidate.get("columns"), list) else []
    by_key = {
        _column_identity(column): column
        for column in candidate_columns
        if isinstance(column, dict) and _column_identity(column)
    }
    for column in table.get("columns", []):
        if not isinstance(column, dict):
            continue
        scope = f"{entity_id}.{column.get('column_id') or column.get('physical_name')}"
        if column_scopes and scope not in column_scopes:
            continue
        candidate_column = by_key.get(_column_identity(column))
        if not candidate_column:
            return f"수정 대상 속성이 LLM 응답에 없습니다: {scope}"
        if str(candidate_column.get("physical_name") or candidate_column.get("column_name") or "") != str(
            column.get("physical_name") or column.get("column_name") or ""
        ):
            return f"보존 대상 물리 컬럼명이 변경되었습니다: {scope}"
        attribute_name = str(
            candidate_column.get("attribute_name") or candidate_column.get("logical_name") or ""
        ).strip()
        if not attribute_name:
            return f"유효한 attribute_name을 생성하지 못했습니다: {scope}"
        column["attribute_name"] = attribute_name
        column["logical_name"] = attribute_name
    return None


def _physical_table_name(table: dict[str, Any]) -> str:
    return str(table.get("table_name") or table.get("physical_name") or "")


def _is_generic_repair_name(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return not text or bool(
        re.fullmatch(
            r"(?:엔티티|entity|table|테이블|데이터|정보|객체|항목|관리|업무)(?:\s*\d+)?",
            text,
        )
    )


def _column_identity(column: dict[str, Any]) -> str:
    return str(column.get("column_id") or column.get("physical_name") or column.get("column_name") or "")


def _extract_tables(document: dict[str, Any]) -> list[Any]:
    for key in ("tables", "entities", "erd_entity_json_list"):
        if isinstance(document.get(key), list):
            return document[key]
    for key in ("raw_json", "final_document_json", "erd_entity_json", "result", "data", "content"):
        value = document.get(key)
        if isinstance(value, dict):
            nested = _extract_tables(value)
            if nested:
                return nested
    for value in document.values():
        if isinstance(value, dict):
            nested = _extract_tables(value)
            if nested:
                return nested
    return []


def _extract_db_design_tables(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if _looks_like_db_design_table(item)]
    if not isinstance(value, dict):
        return []
    for key in ("db_design_json", "final_document_json", "raw_json", "result", "data", "content"):
        nested = value.get(key)
        if isinstance(nested, (dict, list)):
            tables = _extract_db_design_tables(nested)
            if tables:
                return tables
    for key in ("tables", "table_list", "db_tables"):
        candidate = value.get(key)
        if isinstance(candidate, list) and _looks_like_db_design_table_list(candidate):
            return [item for item in candidate if isinstance(item, dict)]
    items = value.get("items")
    if isinstance(items, list) and _looks_like_db_design_table_list(items):
        return [item for item in items if isinstance(item, dict)]
    return []


def _looks_like_db_design_table_list(items: Any) -> bool:
    return isinstance(items, list) and any(_looks_like_db_design_table(item) for item in items)


def _looks_like_db_design_table(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    if not isinstance(item.get("columns"), list) or not item["columns"]:
        return False
    has_table_name = any(item.get(key) for key in ("table_name", "table_id", "physical_name"))
    has_db_column = any(
        isinstance(column, dict)
        and any(column.get(key) for key in ("column_name", "column_id", "physical_name"))
        for column in item["columns"]
    )
    return bool(has_table_name and has_db_column)


def _normalize_existing_db_design(tables: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "database_id": "DB-001",
        "database_name": "업무 DB",
        "storage_group": "업무 기준에 따름",
        "bufferpool": "업무 기준에 따름",
        "index_bufferpool": "업무 기준에 따름",
        "tables": [
            _normalize_db_table(table, index)
            for index, table in enumerate(tables)
            if isinstance(table, dict)
        ],
    }


def _mermaid_entity_from_table(table: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": table.get("entity_name") or table.get("logical_name") or table.get("physical_name") or table.get("table_name"),
        "entity_name": table.get("entity_name") or table.get("logical_name"),
        "table_name": table.get("table_name") or table.get("physical_name"),
        "physical_name": table.get("physical_name") or table.get("table_name"),
        "logical_name": table.get("logical_name") or table.get("table_korean_name"),
        "domain_group": table.get("domain_group", ""),
        "importance_score": table.get("importance_score", 0),
        "relation_count": table.get("relation_count", 0),
        "columns": [
            {
                **column,
                "attribute_name": column.get("attribute_name") or column.get("logical_name"),
                "column_name": column.get("column_name") or column.get("physical_name"),
            }
            for column in table.get("columns", [])
            if isinstance(column, dict)
        ],
    }


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


def _extract_llm_items(value: Any, item_key: str, list_key: str) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        if isinstance(value.get(list_key), list):
            return [item for item in value[list_key] if isinstance(item, dict)]
        if isinstance(value.get(item_key), dict):
            return [value[item_key]]
        if isinstance(value.get("items"), list):
            return [item for item in value["items"] if isinstance(item, dict)]
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _normalize_domain_groups(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        name = str(item.get("domain_name") or item.get("name") or item.get("group_name") or f"도메인 {index + 1}")
        if name in seen:
            continue
        seen.add(name)
        source_ids = item.get("source_requirement_ids") or item.get("source_req_ids") or []
        groups.append(
            {
                **item,
                "domain_id": str(item.get("domain_id") or f"DOMAIN-{len(groups) + 1:03d}"),
                "domain_name": name,
                "source_requirement_ids": [str(value) for value in source_ids] if isinstance(source_ids, list) else [str(source_ids)],
                "description": _short_text(item.get("description") or item.get("detail_text") or name, 120),
            }
        )
    return groups


def _normalize_entities(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entities = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        name = str(item.get("logical_name") or item.get("entity_name") or item.get("name") or f"엔티티 {index + 1}")
        if name in seen:
            continue
        seen.add(name)
        source_ids = item.get("source_requirement_ids") or item.get("source_req_ids") or []
        entities.append(
            {
                **item,
                "entity_id": str(item.get("entity_id") or f"ENT-{len(entities) + 1:03d}"),
                "logical_name": name,
                "description": _short_text(item.get("description") or name, 120),
                "source_requirement_ids": [str(value) for value in source_ids] if isinstance(source_ids, list) else [str(source_ids)],
            }
        )
    return entities


def _normalize_db_table(item: dict[str, Any], index: int) -> dict[str, Any]:
    table_name = str(item.get("table_name") or item.get("physical_name") or f"table_{index + 1}")
    table_id = str(item.get("table_id") or item.get("physical_name") or table_name)
    table_logical_name = str(item.get("table_logical_name") or item.get("logical_name") or table_name)
    columns = item.get("columns") if isinstance(item.get("columns"), list) else []
    normalized_columns = []
    for column_index, column in enumerate(columns):
        if not isinstance(column, dict):
            continue
        column_name = str(column.get("column_name") or column.get("physical_name") or column.get("column_id") or f"column_{column_index + 1}")
        column_id = str(column.get("column_id") or column.get("physical_name") or column_name)
        constraints = column.get("constraints") if isinstance(column.get("constraints"), list) else []
        pk = str(column.get("pk") or ("Y" if "PK" in constraints else ""))
        fk = str(column.get("fk") or ("Y" if "FK" in constraints else ""))
        nullable = column.get("nullable", False if pk == "Y" else True)
        normalized_columns.append(
            {
                **column,
                "column_name": column_name,
                "column_id": column_id,
                "column_logical_name": display_column_name(
                    column.get("column_logical_name") or column.get("logical_name") or column.get("description"),
                    column_name,
                    table_name,
                    pk == "Y",
                ),
                "data_type": str(column.get("data_type") or "VARCHAR(255)"),
                "type_and_length": format_type_and_length(
                    column.get("type_and_length") or column.get("data_type") or "VARCHAR(255)",
                    column.get("length"),
                ),
                "nullable": nullable,
                "not_null": str(column.get("not_null") or ("Y" if not bool(nullable) else "")),
                "pk": pk,
                "fk": fk,
                "idx": str(column.get("idx") or column.get("inx") or ("Y" if pk == "Y" or fk == "Y" else "")),
                "default": column.get("default", ""),
                "description": str(column.get("description") or column.get("logical_name") or ""),
                "constraint": _db_column_constraint(column),
                "constraints": constraints,
            }
        )
    if not normalized_columns:
        normalized_columns = [
            {
                "column_name": f"{table_name.removeprefix('tbl_')}_sn",
                "column_id": f"{table_name.removeprefix('tbl_')}_sn",
                "column_logical_name": "일련번호",
                "data_type": "BIGINT",
                "type_and_length": "BIGINT",
                "nullable": False,
                "not_null": "Y",
                "pk": "Y",
                "fk": "",
                "idx": "Y",
                "default": "",
                "description": "기본키",
                "constraint": "",
                "constraints": ["PK"],
            }
        ]
    return {
        **item,
        "table_id": table_id,
        "table_name": table_name,
        "table_logical_name": table_logical_name,
        "database_name": str(item.get("database_name") or "업무 DB"),
        "tablespace_name": str(item.get("tablespace_name") or f"TS_{table_name.removeprefix('tbl_').upper()}"[:30]),
        "trigger_config": str(item.get("trigger_config") or "해당 없음"),
        "table_description": str(item.get("table_description") or item.get("description") or item.get("logical_name") or table_name),
        "initial_count": str(item.get("initial_count") or "0"),
        "daily_growth": str(item.get("daily_growth") or "산정 필요"),
        "retention_period": str(item.get("retention_period") or "업무 기준에 따름"),
        "max_count": str(item.get("max_count") or "산정 필요"),
        "capacity": str(item.get("capacity") or "산정 필요"),
        "note": str(item.get("note") or ""),
        "columns": normalized_columns,
        "constraints": item.get("constraints") if isinstance(item.get("constraints"), list) else _db_constraints(normalized_columns),
        "indexes": item.get("indexes") if isinstance(item.get("indexes"), list) else [],
    }


def _merge_db_design(base: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """LLM 보강 결과를 반영하되 ERD에서 온 컬럼명/ID/타입/키 구조는 보존합니다."""

    base_tables = [_normalize_db_table(item, index) for index, item in enumerate(base.get("tables") or []) if isinstance(item, dict)]
    candidate_tables = [
        _normalize_db_table(item, index)
        for index, item in enumerate(candidate.get("tables") or [])
        if isinstance(item, dict)
    ]
    candidate_by_key = {
        _db_table_key(table): table
        for table in candidate_tables
        if _db_table_key(table)
    }

    merged_tables = []
    for base_table in base_tables:
        candidate_table = candidate_by_key.get(_db_table_key(base_table), {})
        merged_table = dict(base_table)
        for key in (
            "database_name",
            "tablespace_name",
            "trigger_config",
            "table_description",
            "initial_count",
            "daily_growth",
            "retention_period",
            "max_count",
            "capacity",
            "note",
        ):
            value = candidate_table.get(key)
            if value not in (None, "", []):
                merged_table[key] = value

        candidate_columns = {
            _db_column_key(column): column
            for column in candidate_table.get("columns", [])
            if isinstance(column, dict) and _db_column_key(column)
        }
        merged_columns = []
        for base_column in merged_table.get("columns", []):
            candidate_column = candidate_columns.get(_db_column_key(base_column), {})
            merged_columns.append(_merge_db_column(base_column, candidate_column))
        merged_table["columns"] = merged_columns
        if isinstance(candidate_table.get("indexes"), list):
            merged_table["indexes"] = candidate_table["indexes"]
        if isinstance(candidate_table.get("constraints"), list):
            merged_table["constraints"] = candidate_table["constraints"]
        merged_tables.append(merged_table)

    return {
        **base,
        **{key: value for key, value in candidate.items() if key != "tables" and value not in (None, "", [])},
        "tables": merged_tables,
    }


def _merge_db_column(base_column: dict[str, Any], candidate_column: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base_column)
    for key in ("description", "default", "constraint"):
        value = candidate_column.get(key)
        if value not in (None, "", []):
            merged[key] = value

    base_constraints = base_column.get("constraints") if isinstance(base_column.get("constraints"), list) else []
    candidate_constraints = candidate_column.get("constraints") if isinstance(candidate_column.get("constraints"), list) else []
    merged["constraints"] = list(dict.fromkeys([*base_constraints, *candidate_constraints]))
    merged["type_and_length"] = format_type_and_length(
        base_column.get("type_and_length") or base_column.get("data_type"),
        base_column.get("length"),
    )
    return merged


def _db_table_key(table: dict[str, Any]) -> str:
    return str(table.get("table_name") or table.get("physical_name") or table.get("table_id") or "").lower()


def _db_column_key(column: dict[str, Any]) -> str:
    return str(column.get("column_name") or column.get("physical_name") or column.get("column_id") or "").lower()


def _db_constraints(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pk_columns = [
        column["column_name"]
        for column in columns
        if "PK" in column.get("constraints", []) or column["column_name"].endswith("_sn")
    ]
    return [{"type": "PK", "columns": [pk_columns[0]]}] if pk_columns else []


def _db_column_constraint(column: dict[str, Any]) -> str:
    explicit = column.get("constraint")
    if explicit not in (None, "", []):
        return str(explicit)
    constraints = column.get("constraints") if isinstance(column.get("constraints"), list) else []
    filtered = [
        str(item)
        for item in constraints
        if str(item).upper() not in {"PK", "FK", "INDEX", "IDX", "NOT NULL"}
    ]
    return "; ".join(filtered)


def _dedupe_results(results: list[Any]) -> list[dict[str, Any]]:
    deduped = []
    seen: set[str] = set()
    for result in results:
        if not isinstance(result, dict):
            continue
        score = float(result.get("score") or 0.0)
        if score and score < 0.2:
            continue
        key = str(result.get("citation") or result.get("content") or result)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(result)
    return deduped


def _merge_rag_results(
    base_results: list[dict[str, Any]],
    extra_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, list[dict[str, Any]]] = {}
    for group in [*base_results, *extra_results]:
        if not isinstance(group, dict):
            continue
        table_id = str(group.get("table_id") or "")
        if not table_id:
            continue
        merged.setdefault(table_id, []).extend(group.get("normalized_results") or [])
    return [
        {"table_id": table_id, "normalized_results": _dedupe_results(items)}
        for table_id, items in merged.items()
    ]


def _short_text(value: Any, max_length: int) -> str:
    text = str(value or "").replace("\n", " ").strip()
    return text if len(text) <= max_length else text[:max_length].rstrip()


def _normalize_relationship_names(
    relationships: list[Any],
    tables: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not relationships:
        return []
    table_names = {table["physical_name"] for table in tables}
    table_by_logical = {str(table.get("logical_name")): table["physical_name"] for table in tables}

    normalized: list[dict[str, Any]] = []
    for index, relationship in enumerate(relationships):
        if not isinstance(relationship, dict):
            continue
        parent = _normalize_relation_table_name(
            str(
                relationship.get("parent_table")
                or relationship.get("to_table")
                or relationship.get("source")
                or ""
            ),
            table_names,
            table_by_logical,
        )
        child = _normalize_relation_table_name(
            str(
                relationship.get("child_table")
                or relationship.get("from_table")
                or relationship.get("target")
                or ""
            ),
            table_names,
            table_by_logical,
        )
        if parent not in table_names or child not in table_names:
            continue
        normalized.append(
            {
                **relationship,
                "relationship_id": str(relationship.get("relationship_id") or f"REL-{index + 1:03d}"),
                "parent_table": parent,
                "child_table": child,
                "to_table": parent,
                "from_table": child,
                "to_column": relationship.get("to_column") or relationship.get("parent_column") or "",
                "from_column": relationship.get("from_column") or relationship.get("child_column") or "",
            }
        )
    return normalized


def _normalize_relation_table_name(
    value: str,
    table_names: set[str],
    table_by_logical: dict[str, str],
) -> str:
    if value in table_names:
        return value
    if value in table_by_logical:
        return table_by_logical[value]
    candidate = table_name(value)
    if candidate in table_names:
        return candidate
    return value
