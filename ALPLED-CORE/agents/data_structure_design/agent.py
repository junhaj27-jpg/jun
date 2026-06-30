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
    db_column_logical_name,
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
from agents.data_structure_design.processors.column_standardizer import (
    primary_key_name,
    table_name,
)
from agents.data_structure_design.pipeline import build_erd_from_requirements
from agents.data_structure_design.pipeline.metadata_enricher import enrich_table_metadata
from agents.data_structure_design.pipeline.relationship_inferer import (
    infer_relationships,
    rank_parent_candidates,
)
from agents.data_structure_design.pipeline.validator import validate_erd
from agents.data_structure_design.meeting_erd_requirements import (
    apply_meeting_erd_requirements,
    build_change_requirements_json,
    build_erd_diff,
    build_requirement_coverage,
    evaluate_meeting_erd_requirements,
    extract_meeting_erd_requirements,
)
from agents.data_structure_design.erd_quality import (
    entity_name_needs_llm_review,
    ensure_primary_keys,
    inspect_erd_quality,
    prepare_erd_quality,
)
from agents.data_structure_design.db_quality import (
    prepare_db_quality,
    tablespace_name,
    valid_table_identifier,
)
from agents.document_merge.processors.artifact_parser import artifact_items
from agents.validation.validators.erd_validator import inspect_entity_consistency
from supervisor.repair import build_repair_instruction


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
        self._entity_name_resolution_trace: list[dict[str, Any]] = []
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
        erd_entity_json, naming_warnings = self._resolve_entity_names(
            erd_entity_json,
            selected,
            rag_results,
        )
        warnings.extend(naming_warnings)
        erd_entity_json, catalog_warnings = self._review_entity_catalog(
            erd_entity_json,
            selected,
            rag_results,
        )
        warnings.extend(catalog_warnings)
        erd_entity_json, final_naming_warnings = self._resolve_entity_names(
            erd_entity_json,
            selected,
            rag_results,
        )
        warnings.extend(final_naming_warnings)
        all_entity_scopes = {
            str(scope)
            for table in erd_entity_json.get("tables", [])
            if isinstance(table, dict)
            for scope in (
                table.get("entity_id"),
                table.get("table_id"),
                _physical_table_name(table),
            )
            if scope
        }
        erd_entity_json, duplicate_name_corrections = (
            _resolve_remaining_semantic_duplicates(
                erd_entity_json,
                all_entity_scopes,
            )
        )
        warnings.extend(duplicate_name_corrections)
        erd_entity_json, consistency_warnings = self._repair_initial_entity_consistency(
            erd_entity_json
        )
        warnings.extend(consistency_warnings)
        unresolved_names = _unresolved_entity_name_scopes(erd_entity_json)
        if unresolved_names:
            return self._failed(
                "ERD_ENTITY_NAME_RESOLUTION_FAILED",
                "논리 엔티티명을 확정하지 못했습니다: " + ", ".join(unresolved_names),
            )
        erd_entity_json = _ensure_erd_contract(erd_entity_json)
        erd_entity_json, relation_resolution_warnings = self._resolve_unmapped_fk_relationships(
            erd_entity_json
        )
        warnings.extend(relation_resolution_warnings)
        erd_entity_json, quality_result = prepare_erd_quality(erd_entity_json)
        erd_entity_json["tables"] = enrich_table_metadata(
            erd_entity_json.get("tables", []),
            erd_entity_json.get("relationships", []),
        )
        warnings.extend(_quality_warnings(quality_result))
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
                "erd_quality_result": quality_result,
                "domain_group_list": domain_groups,
                "entity_candidate_list": entity_candidates,
                "entity_name_resolution_trace": self._entity_name_resolution_trace,
                "table_candidate_list": tables,
                "rag_results": rag_results,
                "standardized_tables": tables,
            },
        )

    def _update_erd(self, document_merge: dict[str, Any], state: WorkflowState) -> dict[str, Any]:
        existing = document_merge.get("existing_output_raw_json")
        requested = document_merge.get("requested_output_raw_json")
        changes = document_merge.get("meeting_change_items")
        if not isinstance(existing, dict) or not existing:
            return self._failed("ERD_EXISTING_OUTPUT_MISSING", "existing_output_raw_json이 필요합니다.")
        if not isinstance(changes, list):
            return self._failed("ERD_MEETING_CHANGE_MISSING", "meeting_change_items가 필요합니다.")
        existing_analysis = self._llm_dict("기존 ERD 구조를 분석하세요.", {"existing_output_raw_json": existing}, "ERD_EXISTING_ANALYSIS_LLM_FAILED")
        existing_tables = normalize_erd_tables(_extract_tables(existing_analysis or existing))
        requested_tables = (
            normalize_erd_tables(_extract_tables(requested))
            if isinstance(requested, dict) and requested
            else []
        )
        tables = deepcopy(requested_tables or existing_tables)
        llm_analysis, warnings = self._parallel_llm_analysis(changes, "회의록 변경사항의 ERD 엔티티, 컬럼, 관계 영향을 분석하세요.")
        tables = _apply_table_changes(tables, changes)
        redesign = self._llm_dict(
            "기존 ERD와 회의록 변경사항을 기반으로 ERD를 재설계하고 JSON으로 반환하세요.",
            {"tables": tables, "meeting_change_items": changes, "llm_analysis": llm_analysis},
            "ERD_REDESIGN_LLM_FAILED",
        )
        redesigned_tables = normalize_erd_tables(_extract_tables(redesign) or tables)
        preservation_source = requested_tables or existing_tables
        tables = _repair_update_table_contracts(
            redesigned_tables,
            preservation_source,
        )
        requested_relationships = (
            requested.get("relationships", [])
            if isinstance(requested, dict)
            and isinstance(requested.get("relationships"), list)
            else []
        )
        relationships, relationship_warnings = self._build_relationships(tables)
        if requested_relationships:
            relationships = _merge_relationship_lists(
                requested_relationships,
                relationships,
            )
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
        warnings.extend(erd_warnings)
        naming_search_warnings, naming_rag_results = self._standard_search(
            erd_entity_json.get("tables", []),
            state,
        )
        warnings.extend(naming_search_warnings)
        erd_entity_json, naming_warnings = self._resolve_entity_names(
            erd_entity_json,
            changes,
            naming_rag_results,
        )
        warnings.extend(naming_warnings)
        erd_entity_json, catalog_warnings = self._review_entity_catalog(
            erd_entity_json,
            changes,
            naming_rag_results,
        )
        warnings.extend(catalog_warnings)
        erd_entity_json, final_naming_warnings = self._resolve_entity_names(
            erd_entity_json,
            changes,
            naming_rag_results,
        )
        warnings.extend(final_naming_warnings)
        unresolved_names = _unresolved_entity_name_scopes(erd_entity_json)
        if unresolved_names:
            return self._failed(
                "ERD_ENTITY_NAME_RESOLUTION_FAILED",
                "논리 엔티티명을 확정하지 못했습니다: " + ", ".join(unresolved_names),
            )
        erd_entity_json = _ensure_erd_contract(erd_entity_json)
        erd_entity_json, relation_resolution_warnings = self._resolve_unmapped_fk_relationships(
            erd_entity_json
        )
        warnings.extend(relation_resolution_warnings)
        if meeting_requirements:
            repaired_tables, repaired_relationships, final_meeting_report = (
                apply_meeting_erd_requirements(
                    erd_entity_json.get("tables", []),
                    erd_entity_json.get("relationships", []),
                    meeting_requirements,
                )
            )
            erd_entity_json["tables"] = normalize_erd_tables(repaired_tables)
            erd_entity_json["relationships"] = repaired_relationships
            meeting_report = _merge_meeting_apply_reports(
                meeting_report,
                final_meeting_report,
            )
        erd_entity_json, quality_result = prepare_erd_quality(erd_entity_json)
        erd_entity_json["tables"] = enrich_table_metadata(
            erd_entity_json.get("tables", []),
            erd_entity_json.get("relationships", []),
        )
        warnings.extend(_quality_warnings(quality_result))
        meeting_validation = evaluate_meeting_erd_requirements(
            erd_entity_json.get("tables", []),
            erd_entity_json.get("relationships", []),
            meeting_requirements,
        )
        diff_summary = build_erd_diff(
            existing_tables,
            existing.get("relationships", [])
            if isinstance(existing.get("relationships"), list)
            else [],
            erd_entity_json.get("tables", []),
            erd_entity_json.get("relationships", []),
        )
        requirement_coverage = build_requirement_coverage(
            erd_entity_json.get("tables", []),
            erd_entity_json.get("relationships", []),
            meeting_requirements,
        )
        impact_analysis = {
            "before_docs_detail_sn": state.get("before_docs_detail_sn"),
            "after_docs_detail_sn": state.get("request_docs_detail_sn"),
            "meeting_minutes_file_sn": (
                state.get("file_list", [None])[0]
                if state.get("file_list")
                else None
            ),
            "change_requirements": build_change_requirements_json(
                meeting_requirements
            ),
            "diff_summary": diff_summary,
            "requirement_coverage": {
                key: requirement_coverage[key]
                for key in ("total", "applied", "partial", "missing")
            },
            "requirement_validation_results": requirement_coverage[
                "requirement_validation_results"
            ],
            "final_erd_json": erd_entity_json,
        }
        erd_mermaid_json, mermaid_warnings = self._build_erd_mermaid_json(erd_entity_json)
        warnings.extend([
            *relationship_warnings,
            *erd_warnings,
            *naming_search_warnings,
            *naming_warnings,
            *mermaid_warnings,
        ])
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
                "erd_quality_result": quality_result,
                "entity_name_resolution_trace": self._entity_name_resolution_trace,
                "impact_analysis": impact_analysis,
            },
        )

    def _create_db(self, document_merge: dict[str, Any], state: WorkflowState) -> dict[str, Any]:
        reference = document_merge.get("reference_erd_json_list")
        if not isinstance(reference, list) or not reference:
            return self._failed("DB_REFERENCE_ERD_MISSING", "reference_erd_json_list가 필요합니다.")
        tables = normalize_erd_tables(reference)
        search_warnings, project_results = self._standard_search(tables, state)
        tables, table_name_warnings, table_name_mapping = self._resolve_db_table_identifiers(
            tables,
            project_results,
        )
        document_merge["reference_erd_json_list"] = tables
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
        final_design, db_quality_result = prepare_db_quality(final_design)
        warnings.extend([
            *search_warnings,
            *table_name_warnings,
            *column_standard_warnings,
            *final_warnings,
            *_quality_warnings(db_quality_result),
        ])
        return self._db_success(
            state,
            final_design,
            warnings,
            {
                "reference_erd_json_list": reference,
                "standardized_tables": standardized_tables,
                "column_standard_results": column_standard_results,
                "llm_analysis": erd_analysis,
                "table_name_mapping": table_name_mapping,
                "db_quality_result": db_quality_result,
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
        design_tables = design.get("tables") if isinstance(design.get("tables"), list) else []
        name_search_warnings, name_rag_results = self._standard_search(design_tables, state)
        resolved_tables, table_name_warnings, table_name_mapping = self._resolve_db_table_identifiers(
            design_tables,
            name_rag_results,
        )
        design["tables"] = resolved_tables
        final_design, final_warnings = self._finalize_db_design(design)
        final_design, db_quality_result = prepare_db_quality(final_design)
        warnings.extend([
            *name_search_warnings,
            *table_name_warnings,
            *final_warnings,
            *_quality_warnings(db_quality_result),
        ])
        return self._db_success(
            state,
            final_design,
            warnings,
            {
                "source_artifacts": artifacts,
                "existing_output_raw_json": existing_raw,
                "meeting_change_items": changes if isinstance(changes, list) else [],
                "llm_analysis": llm_analysis,
                "table_name_mapping": table_name_mapping,
                "db_quality_result": db_quality_result,
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
                "각 관계에는 parent_table, parent_column, child_table, child_column을 반드시 포함하고, "
                "parent_column은 실제 PK, child_column은 실제 FK 컬럼이어야 합니다. "
                "JSON으로 relationship_list 또는 relationships를 반환하세요."
            ),
            {"tables": tables, "fallback_relationships": fallback},
            "ERD_RELATION_LLM_FAILED",
        )
        relationships = value.get("relationship_list") or value.get("relationships") if isinstance(value, dict) else None
        return relationships if isinstance(relationships, list) and relationships else fallback, []

    def _resolve_unmapped_fk_relationships(
        self,
        document: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """규칙으로 확정하지 못한 FK를 기존 PK 후보 중에서만 LLM으로 선택합니다."""

        result = deepcopy(document)
        # 물리 키 완전일치처럼 확실한 관계는 먼저 Rule로 보완합니다.
        result, _ = prepare_erd_quality(result)
        tables = [table for table in result.get("tables", []) if isinstance(table, dict)]
        relationships = [
            relation for relation in result.get("relationships", []) if isinstance(relation, dict)
        ]
        mapped = {
            (
                str(relation.get("child_table") or relation.get("from_table") or ""),
                str(relation.get("child_column") or relation.get("from_column") or ""),
            )
            for relation in relationships
        }
        unresolved: list[tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]] = []
        warnings: list[dict[str, Any]] = []
        for table in tables:
            child_table = str(table.get("table_name") or table.get("physical_name") or "")
            for column in table.get("columns", []):
                if not isinstance(column, dict) or not _column_is_fk(column):
                    continue
                child_column = str(column.get("column_name") or column.get("physical_name") or "")
                if not child_table or not child_column or (child_table, child_column) in mapped:
                    continue
                candidates = rank_parent_candidates(tables, child_table, column)
                if not candidates or int(candidates[0]["score"]) < 50:
                    _clear_unsubstantiated_fk(column)
                    warnings.append(
                        {
                            "code": "ERD_FK_FLAG_CLEARED_NO_PARENT",
                            "message": (
                                "참조 가능한 부모 PK 근거가 없어 FK 표시를 해제했습니다."
                            ),
                            "target_scope": [f"{child_table}.{child_column}"],
                        }
                    )
                    continue
                unresolved.append((table, column, candidates[:5]))

        if not unresolved:
            result["relationships"] = relationships
            return result, warnings
        if self.llm_client is None:
            return result, warnings + [
                {
                    "code": "ERD_FK_RELATION_LLM_UNAVAILABLE",
                    "message": "모호한 FK 관계를 확정할 LLM이 설정되지 않았습니다.",
                    "target_scope": [
                        f"{_physical_table_name(table)}.{_physical_column_name(column)}"
                        for table, column, _ in unresolved
                    ],
                }
            ]

        requests = []
        for table, column, candidates in unresolved:
            requests.append(
                {
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "너는 범용 논리/물리 데이터 모델 관계 검토자입니다. 주어진 FK 컬럼이 참조할 부모를 "
                                "candidate_parents 중에서만 선택하세요. 컬럼 논리명, 물리명, 타입, 부모 엔티티명과 PK를 "
                                "함께 비교하세요. 후보가 모호하거나 근거가 부족하면 no_relation=true를 반환하세요. "
                                "새 테이블, 새 컬럼, 후보 밖 관계는 만들지 마세요. JSON으로 parent_table, "
                                "parent_column, confidence, no_relation을 반환하세요."
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "child_table": _physical_table_name(table),
                                    "child_entity_name": table.get("entity_name")
                                    or table.get("logical_name"),
                                    "fk_column": {
                                        "column_name": _physical_column_name(column),
                                        "logical_name": column.get("attribute_name")
                                        or column.get("logical_name")
                                        or column.get("column_logical_name"),
                                        "data_type": column.get("data_type"),
                                    },
                                    "candidate_parents": candidates,
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ],
                    "temperature": 0.0,
                    "max_tokens": 256,
                    "extra_body": {"response_format": {"type": "json_object"}},
                }
            )
        responses = send_parallel(
            requests,
            client=self.llm_client,
            max_workers=self.max_parallel_workers,
        )
        if not responses["success"]:
            return result, [
                {
                    "code": "ERD_FK_RELATION_LLM_FAILED",
                    "message": responses["error"]["message"],
                }
            ]

        for (table, column, candidates), response in zip(unresolved, responses["data"]):
            parsed_value = (
                _parse_repair_response(response["data"])
                if response and response["success"]
                else None
            )
            value = parsed_value if isinstance(parsed_value, dict) else {}
            selection = _extract_relationship_selection(value)
            child_table = _physical_table_name(table)
            child_column = _physical_column_name(column)
            parent_table = str(
                selection.get("parent_table")
                or selection.get("to_table")
                or selection.get("referenced_table")
                or ""
            )
            parent_column = str(
                selection.get("parent_column")
                or selection.get("to_column")
                or selection.get("referenced_column")
                or ""
            )
            if parent_table and not parent_column:
                matching_columns = {
                    str(candidate["parent_column"])
                    for candidate in candidates
                    if str(candidate["parent_table"]) == parent_table
                }
                if len(matching_columns) == 1:
                    parent_column = next(iter(matching_columns))
            candidate_table_names = {
                str(candidate["parent_table"]) for candidate in candidates
            }
            if parent_table and parent_table not in candidate_table_names:
                logical_matches = {
                    str(candidate["parent_table"])
                    for candidate in candidates
                    if str(candidate.get("parent_entity_name") or "").strip().lower()
                    == parent_table.strip().lower()
                }
                if len(logical_matches) == 1:
                    parent_table = next(iter(logical_matches))
                    matching_columns = {
                        str(candidate["parent_column"])
                        for candidate in candidates
                        if str(candidate["parent_table"]) == parent_table
                    }
                    if len(matching_columns) == 1:
                        parent_column = next(iter(matching_columns))
            allowed = {
                (str(candidate["parent_table"]), str(candidate["parent_column"]))
                for candidate in candidates
            }
            if (parent_table, parent_column) not in allowed:
                warnings.append(
                    {
                        "code": "ERD_FK_RELATION_LLM_INVALID",
                        "message": "LLM이 허용된 부모 후보 밖의 관계를 반환했습니다.",
                        "target_scope": [f"{child_table}.{child_column}"],
                    }
                )
                continue
            confidence_value = selection.get("confidence")
            confidence = _float_value(confidence_value)
            selected_candidate = next(
                candidate
                for candidate in candidates
                if (
                    str(candidate["parent_table"]),
                    str(candidate["parent_column"]),
                )
                == (parent_table, parent_column)
            )
            top_score = int(candidates[0]["score"])
            next_score = int(candidates[1]["score"]) if len(candidates) > 1 else 0
            safe_without_confidence = (
                selected_candidate is candidates[0]
                and top_score >= 50
                and (len(candidates) == 1 or top_score - next_score >= 15)
            )
            if (
                selection.get("no_relation")
                or (
                    confidence_value not in (None, "")
                    and confidence < 0.75
                )
                or (
                    confidence_value in (None, "")
                    and not safe_without_confidence
                )
            ):
                warnings.append(
                    {
                        "code": "ERD_FK_RELATION_UNRESOLVED",
                        "message": "FK 부모 후보의 근거가 부족하여 관계를 자동 생성하지 않았습니다.",
                        "target_scope": [f"{child_table}.{child_column}"],
                    }
                )
                continue
            key = (parent_table, parent_column, child_table, child_column)
            if any(
                (
                    str(item.get("parent_table") or item.get("to_table") or ""),
                    str(item.get("parent_column") or item.get("to_column") or ""),
                    str(item.get("child_table") or item.get("from_table") or ""),
                    str(item.get("child_column") or item.get("from_column") or ""),
                )
                == key
                for item in relationships
            ):
                continue
            relationships.append(
                {
                    "relationship_id": f"REL-{len(relationships) + 1:03d}",
                    "parent_table": parent_table,
                    "parent_column": parent_column,
                    "child_table": child_table,
                    "child_column": child_column,
                    "to_table": parent_table,
                    "to_column": parent_column,
                    "from_table": child_table,
                    "from_column": child_column,
                    "relationship_type": "N:1",
                    "description": "references",
                    "resolution_source": "LLM_CANDIDATE_SELECTION",
                }
            )
        result["relationships"] = relationships
        return result, warnings

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
                "entity_name은 요구사항 문장이 아닌 24자 이내의 짧은 업무 객체 명사형으로 통일하고, 동일 개념은 중복 생성하지 마세요. "
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

        entity_target_ids = set(
            instruction.get("target_scope", {}).get("entity_ids") or []
        )
        table_target_ids = set(
            instruction.get("target_scope", {}).get("table_ids") or []
        )
        scoped_tables = [
            table
            for table in current.get("tables", [])
            if isinstance(table, dict)
            and {
                str(table.get("entity_id") or ""),
                str(table.get("table_id") or ""),
                _physical_table_name(table),
            }
            & (entity_target_ids | table_target_ids)
        ]
        failure_types = set(
            instruction.get("failure_types") or [instruction.get("failure_type")]
        )
        relationship_scopes = set(
            instruction.get("target_scope", {}).get("relationship_scopes") or []
        )
        if (
            not scoped_tables
            and not table_target_ids
            and "FK_RELATION_MISSING" not in failure_types
        ):
            return self._failed(
                "REPAIR_SCOPE_INVALID",
                "repair_instruction의 대상 테이블 또는 엔티티를 찾을 수 없습니다.",
            )

        repaired = deepcopy(current)
        candidate_tables: list[dict[str, Any]] = []
        repair_warnings: list[dict[str, Any]] = []
        if "ERD_PK_MISSING" in failure_types:
            repaired, pk_corrections = ensure_primary_keys(
                repaired,
                table_target_ids or entity_target_ids,
            )
            repair_warnings.extend(
                {
                    "code": "ERD_PK_INFERRED",
                    "message": f"{item['target']} 컬럼을 PK로 보정했습니다.",
                }
                for item in pk_corrections
                if item.get("type") == "PRIMARY_KEY_INFERRED"
            )
            remaining_pk_targets = [
                str(table.get("table_id") or table.get("entity_id") or _physical_table_name(table))
                for table in repaired.get("tables", [])
                if isinstance(table, dict)
                and (
                    not (table_target_ids or entity_target_ids)
                    or {
                        str(table.get("table_id") or ""),
                        str(table.get("entity_id") or ""),
                        _physical_table_name(table),
                    }
                    & (table_target_ids or entity_target_ids)
                )
                and not any(
                    _has_column_key(column, "PK")
                    for column in table.get("columns", [])
                    if isinstance(column, dict)
                )
            ]
            if remaining_pk_targets:
                return self._repair_failed(
                    previous,
                    "ERD_REPAIR_PK_UNRESOLVED",
                    "PK 후보를 규칙으로 확정하지 못했습니다: "
                    + ", ".join(remaining_pk_targets),
                )
        if scoped_tables and failure_types != {"ERD_PK_MISSING"}:
            candidate_tables, repair_errors = self._repair_erd_candidates_parallel(
                instruction,
                scoped_tables,
            )
            if repair_errors:
                return self._repair_failed(
                    previous,
                    "ERD_REPAIR_PARTIAL",
                    "일부 엔티티 Repair 응답을 적용하지 못했습니다: "
                    + "; ".join(repair_errors),
                )
            if not candidate_tables:
                return self._repair_failed(
                    previous,
                    "ERD_REPAIR_EMPTY",
                    "제한 수정 대상에 대한 유효한 Repair 응답이 없습니다.",
                )
            if candidate_tables:
                partial_instruction = deepcopy(instruction)
                partial_instruction.setdefault("target_scope", {})["entity_ids"] = [
                    str(table.get("entity_id"))
                    for table in candidate_tables
                    if table.get("entity_id")
                ]
                repaired, error = _merge_scoped_erd_repair(
                    repaired, candidate_tables, partial_instruction
                )
                if error:
                    return self._repair_failed(
                        previous, "ERD_REPAIR_CONSTRAINT_VIOLATION", error
                    )
        if "FK_RELATION_MISSING" in failure_types:
            repaired, relation_warnings = self._resolve_unmapped_fk_relationships(
                repaired
            )
            repair_warnings.extend(relation_warnings)
            unresolved = _unresolved_fk_scopes(repaired)
            remaining_targets = sorted(
                scope for scope in relationship_scopes if scope in unresolved
            )
            if remaining_targets:
                return self._repair_failed(
                    previous,
                    "ERD_REPAIR_RELATION_UNRESOLVED",
                    "FK 관계를 확정하지 못했습니다: "
                    + ", ".join(remaining_targets),
                )
        if "ENTITY_SEMANTIC_DUPLICATED" in failure_types:
            repaired, semantic_corrections = _resolve_remaining_semantic_duplicates(
                repaired,
                entity_target_ids | table_target_ids,
            )
            repair_warnings.extend(semantic_corrections)
        if failure_types & {
            "ENTITY_GENERIC_NAME",
            "ENTITY_NAME_MISMATCH",
            "ENTITY_DESCRIPTION_MISMATCH",
        }:
            repaired, consistency_corrections = (
                _resolve_remaining_name_description_mismatches(
                    repaired,
                    entity_target_ids | table_target_ids,
                )
            )
            repair_warnings.extend(consistency_corrections)
        if "ENTITY_ATTRIBUTE_MISMATCH" in failure_types:
            repaired, attribute_corrections = _resolve_remaining_attribute_mismatches(
                repaired,
                set(instruction.get("target_scope", {}).get("column_scopes") or []),
            )
            repair_warnings.extend(attribute_corrections)
        if failure_types & {
            "ENTITY_GENERIC_NAME",
            "ENTITY_NAME_MISMATCH",
            "ENTITY_SEMANTIC_DUPLICATED",
        }:
            repaired, semantic_corrections = _resolve_remaining_semantic_duplicates(
                repaired,
                entity_target_ids | table_target_ids,
            )
            repair_warnings.extend(semantic_corrections)
        if "FK_RELATION_MISSING" in failure_types:
            repaired, quality_result = prepare_erd_quality(repaired)
        else:
            quality_result = inspect_erd_quality(repaired)
        repair_validation_report = {
            **quality_result,
            "errors": [
                *quality_result.get("errors", []),
                *_entity_consistency_quality_issues(repaired.get("tables", [])),
            ],
        }
        remaining_repair_issues = _remaining_repair_quality_issues(
            repair_validation_report,
            failure_types,
            entity_target_ids | table_target_ids,
        )
        if remaining_repair_issues:
            return self._repair_failed(
                previous,
                "ERD_REPAIR_VALIDATION_FAILED",
                "Repair 후에도 대상 품질 오류가 남아 있습니다: "
                + "; ".join(remaining_repair_issues),
            )
        mermaid_json = {
            "entities": [_mermaid_entity_from_table(table) for table in repaired.get("tables", [])],
            "relationships": repaired.get("relationships", []),
        }
        return self._erd_success(
            state,
            repaired,
            mermaid_json,
            [*repair_warnings, *_quality_warnings(quality_result)],
            {
                "repair_instruction": instruction,
                "repair_candidates": candidate_tables,
                "erd_quality_result": quality_result,
                "entity_name_resolution_trace": self._entity_name_resolution_trace,
            },
        )

    def _repair_erd_candidates_parallel(
        self,
        instruction: dict[str, Any],
        scoped_tables: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """수정 대상별 작은 JSON patch를 병렬 요청하여 응답 잘림을 방지합니다."""

        requests = []
        request_instructions: list[dict[str, Any]] = []
        for table in scoped_tables:
            entity_id = str(table.get("entity_id") or "")
            request_instruction = _scoped_repair_instruction(instruction, table)
            if "ENTITY_SEMANTIC_DUPLICATED" in set(
                request_instruction.get("failure_types")
                or [request_instruction.get("failure_type")]
            ):
                current_name = str(
                    table.get("entity_name") or table.get("logical_name") or ""
                ).strip()
                request_instruction["forbidden_entity_names"] = [current_name] if current_name else []
            target_columns = {
                scope.split(".", 1)[1]
                for scope in instruction.get("target_scope", {}).get("column_scopes", [])
                if str(scope).startswith(f"{entity_id}.") and "." in str(scope)
            }
            compact_columns = [
                {
                    "column_id": column.get("column_id"),
                    "attribute_name": column.get("attribute_name")
                    or column.get("logical_name"),
                    "column_name": column.get("column_name")
                    or column.get("physical_name"),
                    "data_type": column.get("data_type"),
                }
                for column in table.get("columns", [])
                if isinstance(column, dict)
                and (
                    not target_columns
                    or str(column.get("column_id") or column.get("physical_name")) in target_columns
                )
            ]
            requests.append(
                {
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "너는 범용 ERD 논리 모델 품질 수정자입니다. 입력된 엔티티 한 개만 수정하세요. "
                                "repair_instruction의 must_fix만 수행하고 must_preserve와 forbidden_changes를 지키세요. "
                                "entity_name은 24자 이하의 짧은 업무 객체 명사형이어야 하며 요구사항 문장, 카테고리명, "
                                "화면명, generic 이름은 금지합니다. 물리 테이블명과 물리 컬럼명은 변경하지 마세요. "
                                "응답은 설명 없이 JSON 객체 하나만 반환하세요. 형식: "
                                "{\"entity_id\":\"\", \"entity_name\":\"\", "
                                "\"entity_description\":\"\", "
                                "\"columns\":[{\"column_id\":\"\", \"attribute_name\":\"\"}]}. "
                                "수정하지 않는 필드는 생략할 수 있습니다."
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "repair_instruction": {
                                        "failure_types": request_instruction.get("failure_types"),
                                        "must_fix": request_instruction.get("must_fix"),
                                        "must_preserve": request_instruction.get("must_preserve"),
                                        "forbidden_changes": request_instruction.get("forbidden_changes"),
                                        "forbidden_entity_names": request_instruction.get("forbidden_entity_names", []),
                                    },
                                    "target_table": {
                                        "entity_id": entity_id,
                                        "entity_name": table.get("entity_name")
                                        or table.get("logical_name"),
                                        "entity_description": table.get("entity_description")
                                        or table.get("description"),
                                        "table_name": _physical_table_name(table),
                                        "columns": compact_columns,
                                    },
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ],
                    "temperature": 0.0,
                    "max_tokens": 1024,
                    "extra_body": {"response_format": {"type": "json_object"}},
                }
            )
            request_instructions.append(request_instruction)
        result = send_parallel(
            requests,
            client=self.llm_client or LLMClient(),
            max_workers=self.max_parallel_workers,
        )
        if not result["success"]:
            return [], [str(result["error"]["message"])]

        candidates: list[dict[str, Any]] = []
        errors: list[str] = []
        for source, response, request_instruction in zip(
            scoped_tables,
            result["data"],
            request_instructions,
        ):
            entity_id = str(source.get("entity_id") or "")
            if not response or not response["success"]:
                message = response["error"]["message"] if response else "empty response"
                patch = self._retry_minimal_entity_name_repair(request_instruction, source)
                if patch:
                    candidates.append(_apply_repair_patch(source, patch))
                    continue
                errors.append(f"{entity_id}: {message}")
                continue
            parsed_value = _parse_repair_response(response["data"])
            if parsed_value is None:
                patch = self._retry_minimal_entity_name_repair(request_instruction, source)
                if patch:
                    candidates.append(_apply_repair_patch(source, patch))
                    continue
                errors.append(f"{entity_id}: JSON parse failed")
                continue
            patch = _extract_repair_patch(parsed_value, entity_id)
            if not patch:
                patch = self._retry_minimal_entity_name_repair(request_instruction, source)
                if patch:
                    candidates.append(_apply_repair_patch(source, patch))
                    continue
                errors.append(f"{entity_id}: repair patch missing")
                continue
            candidates.append(_apply_repair_patch(source, patch))
        return candidates, errors

    def _retry_minimal_entity_name_repair(
        self,
        instruction: dict[str, Any],
        source: dict[str, Any],
        rag_evidence: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """구조 근거 후보를 만들고 LLM은 후보 선택만 수행합니다."""

        failure_types = set(instruction.get("failure_types") or [instruction.get("failure_type")])
        if not failure_types & {
            "ENTITY_GENERIC_NAME",
            "ENTITY_NAME_MISMATCH",
            "ENTITY_NAME_OVERLONG",
            "ENTITY_NAME_SENTENCE",
            "ENTITY_SEMANTIC_DUPLICATED",
        }:
            return {}
        entity_id = str(source.get("entity_id") or "")
        compact_evidence = _compact_entity_name_evidence(source, rag_evidence or [])
        scored_candidates = _scored_grounded_entity_name_candidates(
            source,
            compact_evidence,
        )
        forbidden_name_keys = {
            _normalized_entity_name_key(value)
            for value in instruction.get("forbidden_entity_names", [])
            if _normalized_entity_name_key(value)
        }
        if forbidden_name_keys:
            scored_candidates = [
                item
                for item in scored_candidates
                if _normalized_entity_name_key(item.get("name")) not in forbidden_name_keys
            ]
        if not scored_candidates:
            self._record_entity_name_resolution(
                entity_id,
                source,
                [],
                "",
                "NO_CANDIDATE",
            )
            return {}
        grounded_candidates = [item["name"] for item in scored_candidates]
        selection_result = (self.llm_client or LLMClient()).chat(
            [
                {
                    "role": "system",
                    "content": (
                        "논리 ERD 엔티티명 선택 작업입니다. candidate_names 중 저장 대상 업무 객체를 "
                        "가장 정확히 나타내는 하나만 선택하세요. 후보를 수정하거나 새 이름을 만들지 마세요. "
                        "요구사항 제목이 아니라 테이블과 속성의 공통 개념을 우선하세요. JSON 한 줄만 "
                        "반환하세요: {\"entity_id\":\"...\",\"entity_name\":\"후보 중 하나\"}"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "entity_id": entity_id,
                            "candidate_names": grounded_candidates,
                            **compact_evidence,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.0,
            max_tokens=128,
            extra_body={"response_format": {"type": "json_object"}},
        )
        selected_name = _entity_name_from_llm_result(selection_result, entity_id)
        selection_source = "LLM_CANDIDATE_SELECTION"
        if selected_name not in grounded_candidates:
            selected_name = grounded_candidates[0]
            selection_source = "TOP_SCORED_CANDIDATE"
        self._record_entity_name_resolution(
            entity_id,
            source,
            scored_candidates,
            selected_name,
            selection_source,
        )
        return {"entity_id": entity_id, "entity_name": selected_name}

    def _record_entity_name_resolution(
        self,
        entity_id: str,
        source: dict[str, Any],
        candidates: list[dict[str, Any]],
        selected_name: str,
        selection_source: str,
    ) -> None:
        trace = getattr(self, "_entity_name_resolution_trace", None)
        if not isinstance(trace, list):
            return
        trace.append(
            {
                "entity_id": entity_id,
                "original_name": source.get("entity_name")
                or source.get("logical_name"),
                "table_name": _physical_table_name(source),
                "candidates": candidates,
                "selected_name": selected_name,
                "selection_source": selection_source,
            }
        )

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
            value = (
                _parse_repair_response(response["data"])
                if response and response["success"]
                else None
            )
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
        parsed_value = _parse_repair_response(result["data"])
        return parsed_value if isinstance(parsed_value, dict) else {}

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
            parsed_value = (
                _parse_repair_response(response["data"])
                if response and response["success"]
                else None
            )
            if parsed_value is not None:
                analyses.append(parsed_value)
            else:
                warnings.append({"code": "DATA_STRUCTURE_LLM_ITEM_FAILED", "message": f"LLM 분석 항목 {index + 1} 처리에 실패했습니다."})
        return analyses, warnings

    def _resolve_entity_names(
        self,
        document: dict[str, Any],
        source_items: list[Any],
        rag_results: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        result = deepcopy(document)
        tables = result.get("tables") if isinstance(result.get("tables"), list) else []
        targets = [table for table in tables if isinstance(table, dict) and _entity_name_needs_resolution(table)]
        if not targets:
            return result, []
        if self.llm_client is None:
            return result, [
                {
                    "code": "ERD_ENTITY_NAME_LLM_UNAVAILABLE",
                    "message": "논리 엔티티명이 없는 테이블을 LLM으로 확정할 수 없습니다.",
                    "target_scope": [str(table.get("entity_id") or table.get("table_id")) for table in targets],
                }
            ]

        rag_by_table = {
            str(item.get("table_id")): item.get("normalized_results", [])
            for item in rag_results
            if isinstance(item, dict)
        }
        requests = []
        for table in targets:
            requests.append(
                {
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "너는 공공 SI 논리 데이터 모델러입니다. 요구사항, 컬럼, 설명, RAG 용어 근거를 종합해 "
                                "저장 대상의 논리 엔티티명을 확정하세요. 화면명·기능명·물리 테이블명은 엔티티명으로 쓰지 말고, "
                                "엔티티/데이터/정보/객체/항목/관리 같은 일반명도 금지합니다. 근거에 없는 업종이나 객체를 만들지 마세요. "
                                "요구사항 문장을 복사하지 말고 24자 이내, 가능하면 2~4개 단어의 짧은 업무 객체 "
                                "명사형으로 작성하세요. '기본사항', '요구사항', '개발 및 운영', '정보를 관리' "
                                "같은 문구는 엔티티명에 포함하지 마세요. "
                                "RAG/LLMOps/AgentOps 같은 기술어는 실제로 독립 저장되는 업무 객체일 때만 엔티티명에 사용하세요. "
                                "JSON으로 entity_name과 entity_description만 반환하세요."
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "table": table,
                                    "source_items": _source_items_for_table(table, source_items),
                                    "rag_results": rag_by_table.get(str(table.get("table_id")), [])[:10],
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ],
                    "temperature": 0.0,
                    "max_tokens": 512,
                    "extra_body": {"response_format": {"type": "json_object"}},
                }
            )
        responses = send_parallel(
            requests,
            client=self.llm_client,
            max_workers=self.max_parallel_workers,
        )
        warnings: list[dict[str, Any]] = []
        if not responses["success"]:
            return result, [{"code": "ERD_ENTITY_NAME_LLM_FAILED", "message": responses["error"]["message"]}]

        for table, response in zip(targets, responses["data"]):
            scope = str(table.get("entity_id") or table.get("table_id") or table.get("table_name") or "")
            parsed_value = (
                _parse_repair_response(response["data"])
                if response and response["success"]
                else None
            )
            candidate = _extract_repair_patch(parsed_value, scope)
            entity_name = str(
                candidate.get("entity_name")
                or candidate.get("logical_name")
                or candidate.get("name")
                or ""
            ).strip()
            if _invalid_resolved_entity_name(entity_name):
                retry_patch = self._retry_minimal_entity_name_repair(
                    {
                        "failure_type": "ENTITY_NAME_SENTENCE",
                        "failure_types": [
                            "ENTITY_NAME_OVERLONG",
                            "ENTITY_NAME_SENTENCE",
                        ],
                    },
                    table,
                    rag_by_table.get(str(table.get("table_id")), [])[:10],
                )
                entity_name = str(retry_patch.get("entity_name") or "").strip()
                if entity_name:
                    candidate = {**candidate, **retry_patch}
            if _invalid_resolved_entity_name(entity_name):
                warnings.append(
                    {
                        "code": "ERD_ENTITY_NAME_RESOLUTION_FAILED",
                        "message": (
                            "이름 전용 LLM 재시도에서도 유효한 논리 엔티티명을 확정하지 못했습니다."
                        ),
                        "target_scope": [scope],
                    }
                )
                table["entity_name"] = ""
                table["logical_name"] = ""
                continue
            table["entity_name"] = entity_name
            table["logical_name"] = entity_name
            description = str(candidate.get("entity_description") or candidate.get("description") or "").strip()
            if description:
                table["entity_description"] = description
                table["description"] = description
                table["table_description"] = description
        return result, warnings

    def _review_entity_catalog(
        self,
        document: dict[str, Any],
        source_items: list[Any],
        rag_results: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if self.llm_client is None:
            return document, []
        result = deepcopy(document)
        tables = [table for table in result.get("tables", []) if isinstance(table, dict)]
        if not tables:
            return result, []
        rag_by_table = {
            str(item.get("table_id")): item.get("normalized_results", [])
            for item in rag_results
            if isinstance(item, dict)
        }
        catalog = []
        for table in tables:
            catalog.append(
                {
                    "table_id": table.get("table_id"),
                    "table_name": table.get("table_name") or table.get("physical_name"),
                    "entity_name": table.get("entity_name") or table.get("logical_name"),
                    "description": table.get("entity_description") or table.get("description"),
                    "attributes": [
                        column.get("attribute_name") or column.get("logical_name")
                        for column in table.get("columns", [])[:8]
                        if isinstance(column, dict)
                    ],
                    "source_requirement_ids": table.get("source_requirement_ids", []),
                    "rag_evidence": [
                        str(item.get("content") or item.get("title") or "")[:300]
                        for item in rag_by_table.get(str(table.get("table_id")), [])[:3]
                        if isinstance(item, dict)
                    ],
                }
            )
        response = self._llm_dict(
            (
                "너는 범용 SI 논리 데이터 모델 품질 검토자입니다. 전체 엔티티 카탈로그를 함께 검토하여 entity_name을 통일하세요. "
                "이름은 24자 이내의 짧은 업무 객체 명사형이어야 하며 요구사항 문장, 카테고리명, 화면명은 금지합니다. "
                "RAG/LLMOps/AgentOps 같은 기술어는 독립적으로 저장·식별·관리되는 객체일 때만 유지하세요. "
                "각 물리 테이블은 서로 다른 저장 역할을 가지므로 entity_name도 전체 카탈로그에서 고유해야 합니다. "
                "개념이 겹치면 물리 테이블명, 설명, 대표 속성에 근거하여 원본·버전·분류·이력·매핑처럼 역할을 구분하세요. "
                "서로 다른 테이블에 같은 entity_name을 제시하거나 duplicate_of를 반환하지 마세요. "
                "물리 테이블명, 컬럼, 관계는 변경하지 마세요. JSON으로 entity_reviews 배열을 반환하세요."
            ),
            {
                "entity_catalog": catalog,
                "source_items": source_items[:20],
            },
            "ERD_ENTITY_CATALOG_LLM_FAILED",
        )
        reviews = response.get("entity_reviews") if isinstance(response, dict) else None
        if not isinstance(reviews, list):
            return result, []
        table_by_id = {str(table.get("table_id") or ""): table for table in tables}
        warnings = []
        for review in reviews:
            if not isinstance(review, dict):
                continue
            table = table_by_id.get(str(review.get("table_id") or ""))
            if table is None:
                continue
            name = str(review.get("entity_name") or "").strip()
            if entity_name_needs_llm_review(name):
                warnings.append(
                    {
                        "code": "ERD_ENTITY_CATALOG_NAME_INVALID",
                        "message": "카탈로그 검토 LLM이 유효하지 않은 엔티티명을 반환했습니다.",
                        "target_scope": [str(table.get("entity_id") or table.get("table_id"))],
                    }
                )
                continue
            table["entity_name"] = name
            table["logical_name"] = name
            description = str(review.get("entity_description") or "").strip()
            if description:
                table["entity_description"] = description
                table["description"] = description
                table["table_description"] = description
            table.pop("semantic_duplicate_of", None)
        return result, warnings

    def _repair_initial_entity_consistency(
        self,
        document: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """최종 Validator 전에 이름·속성·설명 불일치를 대상 제한형으로 보정합니다."""

        result = deepcopy(document)
        warnings: list[dict[str, Any]] = []
        for repair_pass in range(1, 4):
            before = inspect_entity_consistency(result.get("tables", []))
            if not any(before.values()):
                break
            repaired, pass_warnings = self._repair_initial_entity_consistency_once(
                result
            )
            warnings.extend(pass_warnings)
            after = inspect_entity_consistency(repaired.get("tables", []))
            result = repaired
            if after == before:
                warnings.append(
                    {
                        "code": "ERD_INITIAL_CONSISTENCY_NO_PROGRESS",
                        "message": f"최초 생성 정합성 보정 {repair_pass}회차에서 더 이상 개선되지 않았습니다.",
                    }
                )
                break
        result, consistency_corrections = _resolve_remaining_name_description_mismatches(
            result,
            set(),
        )
        warnings.extend(consistency_corrections)
        remaining_consistency = inspect_entity_consistency(result.get("tables", []))
        remaining_attribute_scopes = set(
            remaining_consistency.get("attribute_mismatches") or []
        )
        if remaining_attribute_scopes:
            result, attribute_corrections = _resolve_remaining_attribute_mismatches(
                result,
                remaining_attribute_scopes,
            )
            warnings.extend(attribute_corrections)
        result, duplicate_corrections = _resolve_remaining_semantic_duplicates(
            result,
            set(),
        )
        warnings.extend(duplicate_corrections)
        return result, warnings

    def _repair_initial_entity_consistency_once(
        self,
        document: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        result = deepcopy(document)
        tables = [table for table in result.get("tables", []) if isinstance(table, dict)]
        consistency = inspect_entity_consistency(tables)
        issue_specs = (
            ("ENTITY_GENERIC_NAME", "generic_names"),
            ("ENTITY_NAME_MISMATCH", "name_mismatches"),
            ("ENTITY_ATTRIBUTE_MISMATCH", "attribute_mismatches"),
            ("ENTITY_DESCRIPTION_MISMATCH", "description_mismatches"),
        )
        failed_checks = [
            {
                "failure_type": failure_type,
                "target_agent": "data_structure_design_agent",
                "target_scope": list(consistency.get(key) or []),
            }
            for failure_type, key in issue_specs
            if consistency.get(key)
        ]
        if not failed_checks:
            return result, []
        instruction = build_repair_instruction(
            {"failed_checks": failed_checks},
            repair_round=0,
        )
        if instruction is None:
            return result, []

        target_entity_ids = set(
            instruction.get("target_scope", {}).get("entity_ids") or []
        )
        scoped_tables = [
            table
            for table in tables
            if str(table.get("entity_id") or "") in target_entity_ids
        ]
        if not scoped_tables:
            return result, [
                {
                    "code": "ERD_INITIAL_REPAIR_SCOPE_EMPTY",
                    "message": "최초 생성 정합성 보정 대상 엔티티를 찾지 못했습니다.",
                }
            ]

        candidates, repair_errors = self._repair_erd_candidates_parallel(
            instruction,
            scoped_tables,
        )
        warnings = [
            {
                "code": "ERD_INITIAL_REPAIR_PARTIAL",
                "message": message,
            }
            for message in repair_errors
        ]
        if candidates:
            partial_instruction = deepcopy(instruction)
            partial_instruction.setdefault("target_scope", {})["entity_ids"] = [
                str(table.get("entity_id"))
                for table in candidates
                if table.get("entity_id")
            ]
            result, merge_error = _merge_scoped_erd_repair(
                result,
                candidates,
                partial_instruction,
            )
            if merge_error:
                return document, [
                    *warnings,
                    {
                        "code": "ERD_INITIAL_REPAIR_CONSTRAINT_VIOLATION",
                        "message": merge_error,
                    },
                ]

        all_scopes = {
            str(scope)
            for table in result.get("tables", [])
            if isinstance(table, dict)
            for scope in (
                table.get("entity_id"),
                table.get("table_id"),
                _physical_table_name(table),
            )
            if scope
        }
        result, duplicate_corrections = _resolve_remaining_semantic_duplicates(
            result,
            all_scopes,
        )
        return result, [*warnings, *duplicate_corrections]

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
                search_context = _table_rag_search_context(table)
                future_map[
                    executor.submit(
                        self.search_tool,
                        f"{search_context} 공공데이터 컬럼 표준명 용어사전",
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
                        f"{search_context} 데이터 개인정보 보안 보관 성능 제약조건",
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

    def _resolve_db_table_identifiers(
        self,
        tables: list[dict[str, Any]],
        rag_results: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        """ERD 근거와 LLM/RAG로 DB 물리 테이블명을 확정합니다."""

        result = deepcopy(tables)
        warnings: list[dict[str, Any]] = []
        mappings: list[dict[str, Any]] = []
        targets: list[dict[str, Any]] = []
        rag_by_table = {
            str(item.get("table_id") or ""): item.get("normalized_results", [])
            for item in rag_results
            if isinstance(item, dict)
        }

        for table in result:
            if not isinstance(table, dict):
                continue
            before = str(
                table.get("physical_name")
                or table.get("table_name")
                or table.get("table_id")
                or ""
            ).strip()
            candidate = next(
                (
                    str(value).strip()
                    for value in (
                        table.get("table_id"),
                        table.get("table_name"),
                        table.get("physical_name"),
                    )
                    if valid_table_identifier(value)
                ),
                "",
            )
            if candidate:
                table["table_name"] = candidate
                table["physical_name"] = candidate
                mappings.append({"before": before, "after": candidate, "source": "ERD_JSON"})
            else:
                targets.append(table)

        if not targets:
            return result, warnings, mappings
        if self.llm_client is None:
            for table in targets:
                fallback = _best_db_table_identifier(table)
                if fallback:
                    before = str(
                        table.get("physical_name")
                        or table.get("table_name")
                        or table.get("table_id")
                        or ""
                    )
                    table["table_name"] = fallback
                    table["physical_name"] = fallback
                    mappings.append(
                        {
                            "before": before,
                            "after": fallback,
                            "source": "ERD_LOGICAL_EVIDENCE",
                        }
                    )
                else:
                    warnings.append(
                        {
                            "code": "DB_TABLE_ID_LLM_UNAVAILABLE",
                            "message": "의미 있는 물리 테이블명을 확정할 LLM이 설정되지 않았습니다.",
                            "target_scope": [_db_table_scope(table)],
                        }
                    )
            return result, warnings, mappings

        requests = []
        for table in targets:
            table_key = str(table.get("table_id") or "")
            requests.append(
                {
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "너는 공공 SI 데이터 표준 전문가입니다. ERD의 논리 엔티티와 표준용어 RAG 근거를 바탕으로 "
                                "물리 테이블 ID 하나를 결정하세요. 반드시 tbl_로 시작하는 의미 있는 영문 소문자 snake_case를 "
                                "사용하세요. 업무 객체의 짧은 명사를 사용하고 요구사항 문장을 그대로 번역하지 마세요. "
                                "unresolved, unknown, temp, hash, UUID, 임의 숫자·난수는 금지합니다. 근거에 없는 산업 용어를 "
                                "만들지 마세요. JSON으로 table_name만 반환하세요."
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "entity_name": table.get("entity_name")
                                    or table.get("table_logical_name")
                                    or table.get("logical_name"),
                                    "entity_description": table.get("entity_description")
                                    or table.get("table_description")
                                    or table.get("description"),
                                    "columns": [
                                        {
                                            "logical_name": column.get("attribute_name")
                                            or column.get("logical_name")
                                            or column.get("column_logical_name"),
                                            "physical_name": column.get("physical_name")
                                            or column.get("column_name"),
                                        }
                                        for column in table.get("columns", [])[:12]
                                        if isinstance(column, dict)
                                    ],
                                    "rag_results": rag_by_table.get(table_key, [])[:10],
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ]
                }
            )

        responses = send_parallel(
            requests,
            client=self.llm_client,
            max_workers=self.max_parallel_workers,
        )
        if not responses["success"]:
            warnings.append({"code": "DB_TABLE_ID_LLM_FAILED", "message": responses["error"]["message"]})
            return result, warnings, mappings

        for table, response in zip(targets, responses["data"]):
            parsed = parse_json_response(response["data"]) if response and response["success"] else None
            value = parsed["data"] if parsed and parsed["success"] and isinstance(parsed["data"], dict) else {}
            candidate = value.get("table_identifier") if isinstance(value.get("table_identifier"), dict) else value
            resolved = str(candidate.get("table_name") or candidate.get("table_id") or "").strip()
            scope = _db_table_scope(table)
            if not valid_table_identifier(resolved):
                resolved = _best_db_table_identifier(table)
                if not resolved:
                    warnings.append(
                        {
                            "code": "DB_TABLE_ID_LLM_INVALID",
                            "message": "LLM과 구조 근거에서 유효한 tbl_ snake_case 테이블명을 확정하지 못했습니다.",
                            "target_scope": [scope],
                        }
                    )
                    continue
                resolution_source = "ERD_LOGICAL_EVIDENCE"
            else:
                resolution_source = "LLM_RAG"
            before = str(table.get("physical_name") or table.get("table_name") or table.get("table_id") or "")
            table["table_name"] = resolved
            table["physical_name"] = resolved
            mappings.append({"before": before, "after": resolved, "source": resolution_source})
        return result, warnings, mappings

    @staticmethod
    def _erd_success(state, erd_entity_json, erd_mermaid_json, warnings, debug):
        output = {
            "status": "SUCCESS",
            "erd_entity_json": erd_entity_json,
            "erd_mermaid_json": erd_mermaid_json,
            "warnings": warnings,
            "errors": [],
        }
        for key in (
            "meeting_change_requirements",
            "meeting_change_reflection",
            "meeting_change_apply_report",
            "impact_analysis",
        ):
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
    ).lower()
    normalized = re.sub(r"[\s_·()/.-]+", "", value)
    for phrase in (
        "개발및운영",
        "운영관리",
        "기본사항",
        "요구사항",
        "정보관리",
        "관리",
        "정보",
    ):
        normalized = normalized.replace(phrase, "")
    return normalized


def _merge_scoped_erd_repair(
    current: dict[str, Any],
    candidates: list[dict[str, Any]],
    instruction: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    """LLM 결과에서 허용된 의미 필드만 반영하고 구조 필드는 강제로 보존합니다."""

    result = deepcopy(current)
    target_ids = set(instruction.get("target_scope", {}).get("entity_ids") or [])
    column_scopes = set(instruction.get("target_scope", {}).get("column_scopes") or [])
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
        table_failure_types = set(
            _scoped_repair_instruction(instruction, table).get("failure_types") or []
        )

        if table_failure_types & {
            "ENTITY_GENERIC_NAME",
            "ENTITY_NAME_MISMATCH",
            "ENTITY_NAME_OVERLONG",
            "ENTITY_NAME_SENTENCE",
            "ENTITY_SEMANTIC_DUPLICATED",
        }:
            name = str(candidate.get("entity_name") or candidate.get("logical_name") or "").strip()
            if _is_generic_repair_name(name):
                return current, f"유효한 entity_name을 생성하지 못했습니다: {entity_id}"
            table["entity_name"] = name
            table["logical_name"] = name
            if "ENTITY_SEMANTIC_DUPLICATED" in table_failure_types:
                table.pop("semantic_duplicate_of", None)

        if "ENTITY_DESCRIPTION_MISMATCH" in table_failure_types:
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

        if "ENTITY_ATTRIBUTE_MISMATCH" in table_failure_types:
            error = _merge_repaired_attributes(table, candidate, entity_id, column_scopes)
            if error:
                return current, error

    missing = target_ids - repaired_ids
    if missing:
        return current, f"ERD에서 수정 대상 엔티티를 찾지 못했습니다: {sorted(missing)}"
    return result, None


def _extract_repair_patch(value: Any, entity_id: str) -> dict[str, Any]:
    if isinstance(value, list):
        return next(
            (
                item
                for item in value
                if isinstance(item, dict)
                and str(item.get("entity_id") or "") == entity_id
            ),
            value[0] if len(value) == 1 and isinstance(value[0], dict) else {},
        )
    if not isinstance(value, dict):
        return {}
    for key in (
        "table",
        "entity",
        "repair_result",
        "entity_name_resolution",
        "result",
        "output",
        "response",
        "data",
    ):
        nested = value.get(key)
        if isinstance(nested, dict):
            return _extract_repair_patch(nested, entity_id)
    for key in ("tables", "entities", "entity_reviews"):
        nested = value.get(key)
        if isinstance(nested, list):
            return _extract_repair_patch(nested, entity_id)
    return value


def _parse_repair_response(response: Any) -> Any | None:
    parsed = parse_json_response(response)
    if parsed["success"]:
        return parsed["data"]
    text = ""
    if isinstance(response, dict):
        try:
            text = str(response["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError):
            text = str(response.get("content") or "")
    else:
        text = str(response or "")
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
    candidates = []
    if "{" in text and "}" in text:
        candidates.append(text[text.find("{") : text.rfind("}") + 1])
    if "[" in text and "]" in text:
        candidates.append(text[text.find("[") : text.rfind("]") + 1])
    for candidate in candidates:
        repaired = parse_json_response(candidate)
        if repaired["success"]:
            return repaired["data"]
    return None


def _apply_repair_patch(
    source: dict[str, Any],
    patch: dict[str, Any],
) -> dict[str, Any]:
    candidate = deepcopy(source)
    for key in ("entity_name", "logical_name", "entity_description", "description", "table_description"):
        value = patch.get(key)
        if value not in (None, ""):
            candidate[key] = value
    patch_name = patch.get("entity_name") or patch.get("logical_name") or patch.get("name")
    if patch_name:
        candidate["entity_name"] = patch_name
        candidate["logical_name"] = patch_name
    if patch.get("entity_description"):
        candidate["description"] = patch["entity_description"]
        candidate["table_description"] = patch["entity_description"]

    patch_columns = patch.get("columns") if isinstance(patch.get("columns"), list) else []
    patch_by_id = {
        str(column.get("column_id") or column.get("column_name") or ""): column
        for column in patch_columns
        if isinstance(column, dict)
    }
    for column in candidate.get("columns", []):
        if not isinstance(column, dict):
            continue
        key = str(column.get("column_id") or column.get("column_name") or column.get("physical_name") or "")
        column_patch = patch_by_id.get(key)
        if not column_patch:
            continue
        attribute_name = str(
            column_patch.get("attribute_name")
            or column_patch.get("logical_name")
            or ""
        ).strip()
        if attribute_name:
            column["attribute_name"] = attribute_name
            column["logical_name"] = attribute_name
    return candidate


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
    return entity_name_needs_llm_review(value)


def _column_is_fk(column: dict[str, Any]) -> bool:
    value = column.get("fk") or column.get("is_fk")
    if isinstance(value, str):
        flag = value.strip().upper() in {"Y", "YES", "TRUE", "1", "FK"}
    else:
        flag = bool(value)
    constraints = {str(item).upper() for item in column.get("constraints", [])}
    return flag or bool(constraints & {"FK", "FOREIGN KEY"})


def _clear_unsubstantiated_fk(column: dict[str, Any]) -> None:
    """부모 PK 근거가 없는 FK 표식만 제거하고 컬럼 자체는 보존합니다."""

    column["fk"] = ""
    column["is_fk"] = False
    column["constraints"] = [
        item
        for item in column.get("constraints", [])
        if str(item).strip().upper() not in {"FK", "FOREIGN KEY"}
    ]


def _physical_column_name(column: dict[str, Any]) -> str:
    return str(column.get("column_name") or column.get("physical_name") or "")


def _has_column_key(column: dict[str, Any], marker: str) -> bool:
    value = column.get(marker.lower())
    if isinstance(value, str):
        explicit = value.strip().upper() in {
            "Y",
            "YES",
            "TRUE",
            "1",
            marker,
        }
    else:
        explicit = bool(value)
    constraints = {
        str(item).upper()
        for item in column.get("constraints", [])
        if str(item)
    }
    return explicit or marker in constraints


def _extract_relationship_selection(value: dict[str, Any]) -> dict[str, Any]:
    current: Any = value
    for _ in range(4):
        if not isinstance(current, dict):
            return {}
        nested = next(
            (
                current.get(key)
                for key in (
                    "relationship",
                    "relation",
                    "selection",
                    "result",
                    "output",
                    "data",
                )
                if isinstance(current.get(key), dict)
            ),
            None,
        )
        if nested is None:
            return current
        current = nested
    return current if isinstance(current, dict) else {}


def _unresolved_fk_scopes(document: dict[str, Any]) -> set[str]:
    relationships = [
        relation
        for relation in document.get("relationships", [])
        if isinstance(relation, dict)
    ]
    mapped = {
        (
            str(relation.get("child_table") or relation.get("from_table") or ""),
            str(relation.get("child_column") or relation.get("from_column") or ""),
        )
        for relation in relationships
    }
    unresolved = set()
    for table in document.get("tables", []):
        if not isinstance(table, dict):
            continue
        table_name = _physical_table_name(table)
        for column in table.get("columns", []):
            if not isinstance(column, dict) or not _column_is_fk(column):
                continue
            column_name = _physical_column_name(column)
            if (table_name, column_name) not in mapped:
                unresolved.add(f"{table_name}.{column_name}")
    return unresolved


def _float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _compact_entity_name_evidence(
    table: dict[str, Any],
    rag_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    attributes: list[str] = []
    for column in table.get("columns", []):
        if not isinstance(column, dict):
            continue
        if _is_common_entity_name_column(column):
            continue
        value = str(
            column.get("attribute_name")
            or column.get("logical_name")
            or column.get("column_logical_name")
            or ""
        ).strip()
        if value and value not in attributes:
            attributes.append(value)
    table_name_value = _physical_table_name(table).removeprefix("tbl_")
    physical_tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", table_name_value.lower())
        if token not in {"tbl", "table"}
    ]
    standard_terms: list[str] = []
    for item in rag_evidence[:10]:
        if not isinstance(item, dict):
            continue
        value = str(item.get("title") or item.get("content") or "").strip()
        if value:
            standard_terms.append(value[:200])
    return {
        "physical_table_tokens": physical_tokens,
        "representative_attributes": attributes[:12],
        "entity_description": str(
            table.get("entity_description")
            or table.get("description")
            or table.get("table_description")
            or ""
        )[:300],
        "standard_term_evidence": standard_terms[:5],
    }


def _is_common_entity_name_column(column: dict[str, Any]) -> bool:
    physical = str(
        column.get("column_name") or column.get("physical_name") or ""
    ).lower()
    logical = re.sub(
        r"\s+",
        "",
        str(
            column.get("attribute_name")
            or column.get("logical_name")
            or column.get("column_logical_name")
            or ""
        ),
    )
    if re.search(
        r"(?:reg|crt|create|created|mdfcn|udt|upd|update|modified|del|use)"
        r"_(?:dt|at|yn|sn)$",
        physical,
    ):
        return True
    return logical in {
        "등록일시",
        "수정일시",
        "생성일시",
        "삭제일시",
        "사용여부",
        "활성여부",
        "등록자일련번호",
        "수정자일련번호",
        "생성자일련번호",
        "삭제자일련번호",
    }


_ENTITY_ATTRIBUTE_SUFFIXES = (
    "일련번호",
    "식별번호",
    "식별자",
    "아이디",
    "ID",
    "Id",
    "id",
    "상태코드",
    "유형코드",
    "구분코드",
    "코드",
    "등록일시",
    "수정일시",
    "생성일시",
    "일시",
    "이름",
    "명칭",
    "설명",
    "내용",
    "여부",
    "번호",
    "순번",
    "버전",
    "명",
)
_GENERIC_PHYSICAL_NAME_TOKENS = {
    "management",
    "manage",
    "create",
    "created",
    "base",
    "basic",
    "default",
    "information",
    "info",
    "data",
    "entity",
    "table",
}
_COMMON_ENTITY_ATTRIBUTE_BASES = {
    "등록",
    "수정",
    "생성",
    "삭제",
    "사용",
    "활성",
    "처리",
    "최초",
    "최종",
    "생성자",
    "수정자",
    "등록자",
    "삭제자",
}
_STRUCTURAL_PHYSICAL_NAME_TOKENS = {
    "version",
    "ver",
    "history",
    "hist",
    "log",
    "detail",
    "mapping",
    "map",
    "config",
    "setting",
    "step",
}


def _scored_grounded_entity_name_candidates(
    table: dict[str, Any],
    compact_evidence: dict[str, Any],
) -> list[dict[str, Any]]:
    """물리명과 대표 속성에 실제로 등장하는 짧은 이름 후보만 구성합니다."""

    candidates: list[str] = []
    support: dict[str, int] = {}
    evidence: dict[str, list[str]] = {}

    def add(value: Any, *, weight: int = 1, source: str) -> None:
        name = re.sub(r"\s+", " ", str(value or "")).strip(" _-/()")
        if not name or entity_name_needs_llm_review(name) or len(name) > 16:
            return
        support[name] = support.get(name, 0) + weight
        if source not in evidence.setdefault(name, []):
            evidence[name].append(source)
        if name not in candidates:
            candidates.append(name)

    for attribute in compact_evidence.get("representative_attributes", []):
        text = re.sub(r"\s+", " ", str(attribute or "")).strip()
        stripped = text
        for suffix in _ENTITY_ATTRIBUTE_SUFFIXES:
            if stripped.endswith(suffix) and len(stripped) > len(suffix):
                stripped = stripped[: -len(suffix)].strip()
                break
        if stripped and stripped != text:
            compact_stripped = re.sub(r"\s+", "", stripped)
            if compact_stripped in _COMMON_ENTITY_ATTRIBUTE_BASES:
                continue
            add(stripped, weight=3, source=f"attribute:{text}")

    description = str(compact_evidence.get("entity_description") or "")
    for pattern in (
        r"^\s*([A-Za-z0-9가-힣][A-Za-z0-9가-힣\s·/-]{0,20}?)\s*정보를\s*관리",
        r"^\s*([A-Za-z0-9가-힣][A-Za-z0-9가-힣\s·/-]{0,20}?)\s*(?:을|를)\s*(?:저장|관리|기록)",
    ):
        match = re.search(pattern, description)
        if match:
            add(match.group(1), weight=2, source="description")

    physical_tokens = [
        str(token).strip()
        for token in compact_evidence.get("physical_table_tokens", [])
        if str(token).strip()
        and str(token).lower() not in _GENERIC_PHYSICAL_NAME_TOKENS
    ]
    structural_label = _entity_structural_role_label(table, physical_tokens)
    base_physical_tokens = [
        token
        for token in physical_tokens
        if token.lower() not in _STRUCTURAL_PHYSICAL_NAME_TOKENS
    ]
    for token in base_physical_tokens:
        add(
            _display_physical_token(token),
            weight=_physical_entity_token_weight(token),
            source=f"physical_token:{token}",
        )
    if 1 < len(base_physical_tokens) <= 3:
        add(
            " ".join(
                _display_physical_token(token)
                for token in base_physical_tokens
            ),
            weight=5,
            source="physical_token_combination",
        )
    if structural_label:
        add(
            structural_label,
            weight=4,
            source=f"structural_role:{structural_label}",
        )
        base_names = [
            name
            for name in list(candidates)
            if name != structural_label and structural_label not in name
        ]
        for base_name in base_names[:5]:
            add(
                f"{base_name} {structural_label}",
                weight=support.get(base_name, 1) + 10,
                source=f"structural_role:{structural_label}",
            )

    ordered = sorted(
        candidates,
        key=lambda item: (-support.get(item, 0), len(item), item.lower()),
    )[:12]
    return [
        {
            "name": name,
            "score": support.get(name, 0),
            "evidence": evidence.get(name, []),
        }
        for name in ordered
    ]


def _physical_entity_token_weight(value: str) -> int:
    token = value.lower()
    if token in {"ai", "ml"}:
        return 1
    if token.endswith("ops"):
        return 9
    if token in {"agent", "llm", "rag", "model", "document", "user"}:
        return 7
    return 5


def _entity_structural_role_label(
    table: dict[str, Any],
    physical_tokens: list[str],
) -> str:
    explicit = str(table.get("table_type") or "").strip().upper()
    tokens = {token.lower() for token in physical_tokens}
    role_labels = {
        "VERSION": "버전",
        "HISTORY": "이력",
        "LOG": "로그",
        "DETAIL": "상세",
        "MAPPING": "매핑",
        "JOB": "작업",
        "JOB_STEP": "작업 단계",
        "CONFIG": "설정",
        "FILE": "파일",
        "APPROVAL": "승인",
        "CODE": "코드",
    }
    if explicit in role_labels:
        return role_labels[explicit]
    token_roles = (
        ("작업 단계", {"job_step", "jobstep"}),
        ("버전", {"version", "ver"}),
        ("이력", {"history", "hist"}),
        ("로그", {"log"}),
        ("상세", {"detail"}),
        ("매핑", {"mapping", "map"}),
        ("설정", {"config", "setting"}),
        ("파일", {"file"}),
        ("승인", {"approval", "approve"}),
        ("작업", {"job", "task"}),
        ("코드", {"code"}),
    )
    joined = "_".join(tokens)
    for label, markers in token_roles:
        if tokens & markers or any(marker in joined for marker in markers):
            return label
    return ""


def _display_physical_token(value: str) -> str:
    logical_tokens = {
        "agent": "Agent",
        "agentops": "AgentOps",
        "appops": "AppOps",
        "approval": "승인",
        "code": "코드",
        "config": "설정",
        "counsel": "상담",
        "dept": "부서",
        "department": "부서",
        "document": "문서",
        "embedding": "임베딩",
        "file": "파일",
        "index": "색인",
        "job": "작업",
        "menu": "메뉴",
        "llmops": "LLMOps",
        "mlops": "MLOps",
        "model": "모델",
        "notification": "알림",
        "product": "상품",
        "prompt": "프롬프트",
        "role": "권한",
        "ragops": "RAGOps",
        "status": "상태",
        "tag": "태그",
        "template": "템플릿",
        "user": "사용자",
    }
    if value.lower() in logical_tokens:
        return logical_tokens[value.lower()]
    upper_tokens = {
        "ai",
        "api",
        "db",
        "erp",
        "fk",
        "id",
        "llm",
        "llmops",
        "ml",
        "mlops",
        "ocr",
        "pk",
        "rag",
        "ui",
        "ux",
    }
    return value.upper() if value.lower() in upper_tokens else value


def _entity_name_from_llm_result(result: dict[str, Any], entity_id: str) -> str:
    if not result.get("success"):
        return ""
    parsed_value = _parse_repair_response(result.get("data"))
    patch = (
        _extract_repair_patch(parsed_value, entity_id)
        if parsed_value is not None
        else {}
    )
    name = str(
        patch.get("entity_name")
        or patch.get("logical_name")
        or patch.get("name")
        or ""
    ).strip()
    return "" if entity_name_needs_llm_review(name) else name


def _unresolved_entity_name_scopes(document: dict[str, Any]) -> list[str]:
    return [
        str(
            table.get("entity_id")
            or table.get("table_id")
            or table.get("table_name")
            or "unknown"
        )
        for table in document.get("tables", [])
        if isinstance(table, dict)
        and entity_name_needs_llm_review(
            table.get("entity_name") or table.get("logical_name")
        )
    ]


def _entity_name_needs_resolution(table: dict[str, Any]) -> bool:
    value = str(table.get("entity_name") or table.get("logical_name") or "").strip()
    return entity_name_needs_llm_review(value)


def _invalid_resolved_entity_name(value: Any) -> bool:
    return entity_name_needs_llm_review(value)


def _quality_warnings(report: dict[str, Any]) -> list[dict[str, Any]]:
    values = []
    for severity, items in (("ERROR", report.get("errors", [])), ("WARNING", report.get("warnings", []))):
        for item in items:
            if not isinstance(item, dict):
                continue
            values.append(
                {
                    "code": str(item.get("code") or "ERD_QUALITY_CHECK"),
                    "message": str(item.get("message") or "ERD 품질 검토가 필요합니다."),
                    "severity": severity,
                    "target_scope": list(item.get("target_scope") or []),
                }
            )
    return values


def _remaining_repair_quality_issues(
    report: dict[str, Any],
    failure_types: set[str],
    target_scopes: set[str],
) -> list[str]:
    """Repair 대상으로 지정된 품질 오류가 남았는지 확인합니다."""

    remaining: list[str] = []
    for issue in report.get("errors", []):
        if not isinstance(issue, dict):
            continue
        code = str(issue.get("code") or "")
        if code not in failure_types:
            continue
        scopes = {str(value) for value in issue.get("target_scope", []) if str(value)}
        scope_roots = {scope.split(".", 1)[0] for scope in scopes}
        target_roots = {scope.split(".", 1)[0] for scope in target_scopes}
        if target_roots and scope_roots and not (target_roots & scope_roots):
            continue
        scope_text = ", ".join(sorted(scopes)) or "unknown"
        remaining.append(f"{code}({scope_text})")
    return remaining


def _entity_consistency_quality_issues(tables: list[Any]) -> list[dict[str, Any]]:
    consistency = inspect_entity_consistency(tables)
    issue_specs = (
        ("ENTITY_GENERIC_NAME", "generic_names"),
        ("ENTITY_NAME_MISMATCH", "name_mismatches"),
        ("ENTITY_ATTRIBUTE_MISMATCH", "attribute_mismatches"),
        ("ENTITY_DESCRIPTION_MISMATCH", "description_mismatches"),
    )
    return [
        {
            "code": failure_type,
            "message": "엔티티 의미 정합성 보정이 필요합니다.",
            "target_scope": list(consistency.get(key) or []),
        }
        for failure_type, key in issue_specs
        if consistency.get(key)
    ]


def _scoped_repair_instruction(
    instruction: dict[str, Any],
    table: dict[str, Any],
) -> dict[str, Any]:
    """각 엔티티에 실제로 해당하는 실패 유형과 수정 규칙만 남깁니다."""

    scoped = deepcopy(instruction)
    scope_values = {
        str(table.get("entity_id") or ""),
        str(table.get("table_id") or ""),
        _physical_table_name(table),
    }
    scoped_failure_types: list[str] = []
    for check in instruction.get("validation_checks", []):
        if not isinstance(check, dict):
            continue
        check_scopes = {
            str(value).split(".", 1)[0]
            for value in check.get("target_scope", [])
            if str(value)
        }
        if not (scope_values & check_scopes):
            continue
        failure_type = str(check.get("failure_type") or "")
        if failure_type and failure_type not in scoped_failure_types:
            scoped_failure_types.append(failure_type)
    if not scoped_failure_types:
        scoped_failure_types = [
            str(value)
            for value in (
                instruction.get("failure_types")
                or [instruction.get("failure_type")]
            )
            if str(value)
        ]

    scoped["failure_types"] = scoped_failure_types
    scoped["failure_type"] = scoped_failure_types[0] if scoped_failure_types else None

    repair_rules = instruction.get("repair_rules") or {}
    selected_rules = [
        repair_rules[failure_type]
        for failure_type in scoped_failure_types
        if isinstance(repair_rules.get(failure_type), dict)
    ]
    if selected_rules:
        scoped["must_fix"] = list(
            dict.fromkeys(
                item
                for rule in selected_rules
                for item in rule.get("must_fix", [])
            )
        )
        must_preserve = list(
            dict.fromkeys(
                item
                for rule in selected_rules
                for item in rule.get("must_preserve", [])
            )
        )
        if set(scoped_failure_types) & {
            "ENTITY_GENERIC_NAME",
            "ENTITY_NAME_MISMATCH",
            "ENTITY_NAME_OVERLONG",
            "ENTITY_NAME_SENTENCE",
            "ENTITY_SEMANTIC_DUPLICATED",
        }:
            must_preserve = [
                item for item in must_preserve if item not in {"entity_name", "logical_name"}
            ]
        if "ENTITY_DESCRIPTION_MISMATCH" in scoped_failure_types:
            must_preserve = [
                item for item in must_preserve if item != "entity_description"
            ]
        if "ENTITY_ATTRIBUTE_MISMATCH" in scoped_failure_types:
            must_preserve = [item for item in must_preserve if item != "columns"]
        if "FK_RELATION_MISSING" in scoped_failure_types:
            must_preserve = [item for item in must_preserve if item != "relationships"]
        scoped["must_preserve"] = must_preserve
    return scoped


def _normalized_entity_name_key(value: Any) -> str:
    return re.sub(r"[\s_-]+", "", str(value or "")).lower()


def _resolve_remaining_semantic_duplicates(
    document: dict[str, Any],
    target_scopes: set[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """LLM Repair 후 남은 중복 논리명을 근거 후보로 분리합니다."""

    result = deepcopy(document)
    tables = [table for table in result.get("tables", []) if isinstance(table, dict)]
    table_by_scope: dict[str, dict[str, Any]] = {}
    for table in tables:
        scopes = {
            str(table.get("entity_id") or ""),
            str(table.get("table_id") or ""),
            _physical_table_name(table),
        }
        for scope in scopes:
            if scope:
                table_by_scope[scope] = table
        if not target_scopes or target_scopes & scopes:
            table.pop("semantic_duplicate_of", None)

    corrections: list[dict[str, Any]] = []
    used_name_keys = {
        _normalized_entity_name_key(
            table.get("entity_name") or table.get("logical_name")
        )
        for table in tables
        if _normalized_entity_name_key(
            table.get("entity_name") or table.get("logical_name")
        )
    }

    for _ in range(max(1, len(tables))):
        report = inspect_erd_quality(result)
        duplicate_issues = [
            issue
            for issue in report.get("errors", [])
            if isinstance(issue, dict)
            and issue.get("code") == "ENTITY_SEMANTIC_DUPLICATED"
        ]
        if not duplicate_issues:
            break

        changed = False
        for issue in duplicate_issues:
            duplicate_tables: list[dict[str, Any]] = []
            for scope in issue.get("target_scope", []):
                table = table_by_scope.get(str(scope))
                if table is not None and table not in duplicate_tables:
                    duplicate_tables.append(table)
            eligible = [
                table
                for table in duplicate_tables
                if not target_scopes
                or target_scopes
                & {
                    str(table.get("entity_id") or ""),
                    str(table.get("table_id") or ""),
                    _physical_table_name(table),
                }
            ]
            # 중복 그룹의 첫 이름은 보존하고 나머지만 근거 기반으로 분리합니다.
            for table in eligible[1:]:
                previous_name = str(
                    table.get("entity_name") or table.get("logical_name") or ""
                ).strip()
                candidates = _scored_grounded_entity_name_candidates(
                    table,
                    _compact_entity_name_evidence(table, []),
                )
                selected_name = next(
                    (
                        str(candidate.get("name") or "").strip()
                        for candidate in candidates
                        if _normalized_entity_name_key(candidate.get("name"))
                        and _normalized_entity_name_key(candidate.get("name"))
                        not in used_name_keys
                    ),
                    "",
                )
                if not selected_name:
                    continue
                table["entity_name"] = selected_name
                table["logical_name"] = selected_name
                table.pop("semantic_duplicate_of", None)
                used_name_keys.add(_normalized_entity_name_key(selected_name))
                corrections.append(
                    {
                        "code": "ENTITY_SEMANTIC_DUPLICATE_RESOLVED",
                        "message": f"{table.get('entity_id') or table.get('table_id')}: {previous_name} -> {selected_name}",
                    }
                )
                changed = True
        if not changed:
            break
    return result, corrections


def _resolve_remaining_attribute_mismatches(
    document: dict[str, Any],
    target_scopes: set[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """LLM이 남긴 대상 속성 불일치를 물리명·접미사 근거로 확정합니다."""

    result = deepcopy(document)
    current_mismatches = set(
        inspect_entity_consistency(result.get("tables", [])).get(
            "attribute_mismatches", []
        )
    )
    targets = current_mismatches & target_scopes if target_scopes else current_mismatches
    corrections: list[dict[str, Any]] = []
    if not targets:
        return result, corrections

    for table in result.get("tables", []):
        if not isinstance(table, dict):
            continue
        entity_id = str(table.get("entity_id") or "")
        entity_name = str(
            table.get("entity_name") or table.get("logical_name") or ""
        ).strip()
        if not entity_id or not entity_name:
            continue
        for column in table.get("columns", []):
            if not isinstance(column, dict):
                continue
            column_id = str(
                column.get("column_id")
                or column.get("physical_name")
                or column.get("column_name")
                or ""
            )
            scope = f"{entity_id}.{column_id}"
            if scope not in targets:
                continue
            previous_name = str(
                column.get("attribute_name") or column.get("logical_name") or ""
            ).strip()
            suffix = _attribute_name_suffix(previous_name, column)
            resolved_name = f"{entity_name} {suffix}".strip()
            column["attribute_name"] = resolved_name
            column["logical_name"] = resolved_name
            corrections.append(
                {
                    "code": "ENTITY_ATTRIBUTE_MISMATCH_RESOLVED",
                    "message": f"{scope}: {previous_name} -> {resolved_name}",
                }
            )
    return result, corrections


def _resolve_remaining_name_description_mismatches(
    document: dict[str, Any],
    target_scopes: set[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """이름·설명 불일치를 물리명·속성·기존 설명 근거로 마무리합니다."""

    result = deepcopy(document)
    tables = [table for table in result.get("tables", []) if isinstance(table, dict)]
    consistency = inspect_entity_consistency(tables)
    name_targets = set(consistency.get("name_mismatches") or [])
    description_targets = set(consistency.get("description_mismatches") or [])
    if target_scopes:
        target_roots = {scope.split(".", 1)[0] for scope in target_scopes}
        name_targets &= target_roots
        description_targets &= target_roots

    used_name_keys = {
        _normalized_entity_name_key(
            table.get("entity_name") or table.get("logical_name")
        )
        for table in tables
        if _normalized_entity_name_key(
            table.get("entity_name") or table.get("logical_name")
        )
    }
    corrections: list[dict[str, Any]] = []
    for table in tables:
        entity_id = str(table.get("entity_id") or "")
        if entity_id in name_targets:
            previous_name = str(
                table.get("entity_name") or table.get("logical_name") or ""
            ).strip()
            current_key = _normalized_entity_name_key(previous_name)
            candidates = _scored_grounded_entity_name_candidates(
                table,
                _compact_entity_name_evidence(table, []),
            )
            selected_name = next(
                (
                    str(candidate.get("name") or "").strip()
                    for candidate in candidates
                    if _normalized_entity_name_key(candidate.get("name"))
                    and _normalized_entity_name_key(candidate.get("name")) != current_key
                    and _normalized_entity_name_key(candidate.get("name"))
                    not in used_name_keys
                ),
                "",
            )
            if selected_name:
                table["entity_name"] = selected_name
                table["logical_name"] = selected_name
                used_name_keys.add(_normalized_entity_name_key(selected_name))
                corrections.append(
                    {
                        "code": "ENTITY_NAME_MISMATCH_RESOLVED",
                        "message": f"{entity_id}: {previous_name} -> {selected_name}",
                    }
                )

        if entity_id in description_targets:
            entity_name = str(
                table.get("entity_name") or table.get("logical_name") or ""
            ).strip()
            previous_description = str(
                table.get("entity_description")
                or table.get("description")
                or table.get("table_description")
                or ""
            ).strip()
            if entity_name:
                resolved_description = f"{entity_name} 정보를 관리합니다."
                if previous_description:
                    resolved_description += f" {previous_description}"
                table["entity_description"] = resolved_description
                table["description"] = resolved_description
                table["table_description"] = resolved_description
                corrections.append(
                    {
                        "code": "ENTITY_DESCRIPTION_MISMATCH_RESOLVED",
                        "message": f"{entity_id}: 설명에 {entity_name} 개념을 반영했습니다.",
                    }
                )
    return result, corrections


def _attribute_name_suffix(value: Any, column: dict[str, Any]) -> str:
    text = str(value or "").strip()
    for suffix in (
        "상태 코드",
        "일련번호",
        "아이디",
        "번호",
        "이름",
        "내용",
        "상태",
        "코드",
        "ID",
        "명",
    ):
        if text.lower().endswith(suffix.lower()):
            return suffix

    physical_name = str(
        column.get("physical_name") or column.get("column_name") or ""
    ).lower()
    token = physical_name.rsplit("_", 1)[-1]
    return {
        "id": "ID",
        "sn": "일련번호",
        "no": "번호",
        "nm": "명",
        "name": "명",
        "cd": "코드",
        "code": "코드",
        "cn": "내용",
        "content": "내용",
        "stts": "상태",
        "status": "상태",
    }.get(token, "값")


def _source_items_for_table(table: dict[str, Any], source_items: list[Any]) -> list[Any]:
    source_ids = {
        str(value)
        for value in (table.get("source_requirement_ids") or table.get("source_req_ids") or [])
        if str(value)
    }
    if not source_ids:
        return source_items[:10]
    matched = []
    for item in source_items:
        if not isinstance(item, dict):
            continue
        item_id = str(
            item.get("requirement_id")
            or item.get("req_id")
            or item.get("source_requirement_id")
            or item.get("change_id")
            or ""
        )
        if item_id in source_ids:
            matched.append(item)
    return matched or source_items[:10]


def _table_rag_search_context(table: dict[str, Any]) -> str:
    values = [
        table.get("entity_name"),
        table.get("table_logical_name"),
        table.get("logical_name"),
        table.get("table_description"),
        table.get("description"),
        table.get("table_name"),
        table.get("physical_name"),
    ]
    values.extend(
        column.get("attribute_name") or column.get("logical_name") or column.get("column_name")
        for column in table.get("columns", [])[:8]
        if isinstance(column, dict)
    )
    return " ".join(dict.fromkeys(str(value).strip() for value in values if str(value or "").strip()))


def _db_table_scope(table: dict[str, Any]) -> str:
    return str(
        table.get("table_id")
        or table.get("entity_id")
        or table.get("entity_name")
        or table.get("table_logical_name")
        or table.get("logical_name")
        or "table"
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


def _merge_relationship_lists(
    primary: list[Any],
    secondary: list[Any],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for relation in [*primary, *secondary]:
        if not isinstance(relation, dict):
            continue
        parent_table = str(
            relation.get("parent_table")
            or relation.get("to_table")
            or relation.get("source")
            or ""
        )
        child_table = str(
            relation.get("child_table")
            or relation.get("from_table")
            or relation.get("target")
            or ""
        )
        parent_column = str(
            relation.get("parent_column")
            or relation.get("to_column")
            or ""
        )
        child_column = str(
            relation.get("child_column")
            or relation.get("from_column")
            or ""
        )
        key = (parent_table, parent_column, child_table, child_column)
        if not parent_table or not child_table or key in seen:
            continue
        seen.add(key)
        merged.append(deepcopy(relation))
    return merged


def _merge_meeting_apply_reports(
    first: dict[str, Any],
    second: dict[str, Any],
) -> dict[str, Any]:
    return {
        "meeting_change_requirements": list(
            second.get("meeting_change_requirements")
            or first.get("meeting_change_requirements")
            or []
        ),
        "added_tables": list(
            dict.fromkeys(
                [
                    *first.get("added_tables", []),
                    *second.get("added_tables", []),
                ]
            )
        ),
        "added_columns": list(
            dict.fromkeys(
                [
                    *first.get("added_columns", []),
                    *second.get("added_columns", []),
                ]
            )
        ),
        "added_relationships": list(
            dict.fromkeys(
                [
                    *first.get("added_relationships", []),
                    *second.get("added_relationships", []),
                ]
            )
        ),
    }


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


def _repair_update_table_contracts(
    redesigned_tables: list[dict[str, Any]],
    existing_tables: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """수정 LLM이 누락한 기존 물리명과 PK를 보존하고 식별자를 복구합니다."""

    existing_by_entity = {
        str(table.get("entity_id") or ""): table
        for table in existing_tables
        if isinstance(table, dict) and table.get("entity_id")
    }
    existing_by_logical = {
        _logical_table_key(table): table
        for table in existing_tables
        if isinstance(table, dict) and _logical_table_key(table)
    }
    repaired = deepcopy(redesigned_tables)
    for table in repaired:
        if not isinstance(table, dict):
            continue
        source = existing_by_entity.get(str(table.get("entity_id") or ""))
        if source is None:
            source = existing_by_logical.get(_logical_table_key(table))
        logical_name = str(
            table.get("entity_name") or table.get("logical_name") or ""
        ).strip()
        physical_name = _physical_table_name(table)
        if physical_name in {
            "",
            "tbl_entity",
            "tbl_table",
            "tbl_data",
            "tbl_info",
            "tbl_object",
            "tbl_item",
        }:
            source_name = _physical_table_name(source or {})
            resolved = source_name if source_name not in {"", "tbl_entity"} else table_name(logical_name)
            if resolved:
                table["table_name"] = resolved
                table["physical_name"] = resolved

        if not any(
            isinstance(column, dict)
            and (
                _column_is_pk(column)
                or "PK"
                in {
                    str(item).upper()
                    for item in column.get("constraints", [])
                }
            )
            for column in table.get("columns", [])
        ):
            source_pk = next(
                (
                    deepcopy(column)
                    for column in (source or {}).get("columns", [])
                    if isinstance(column, dict)
                    and (
                        _column_is_pk(column)
                        or "PK"
                        in {
                            str(item).upper()
                            for item in column.get("constraints", [])
                        }
                    )
                ),
                None,
            )
            if source_pk is None:
                pk_name = primary_key_name(logical_name) or (
                    _physical_table_name(table).removeprefix("tbl_") + "_sn"
                )
                source_pk = {
                    "attribute_name": f"{logical_name} 일련번호",
                    "logical_name": f"{logical_name} 일련번호",
                    "column_name": pk_name,
                    "physical_name": pk_name,
                    "data_type": "BIGINT",
                    "nullable": False,
                    "pk": "Y",
                    "idx": "Y",
                    "constraints": ["PK", "AUTO_INCREMENT"],
                    "description": f"{logical_name} 일련번호",
                }
            source_pk["pk"] = "Y"
            source_pk["idx"] = "Y"
            constraints = [
                str(item) for item in source_pk.get("constraints", []) if str(item)
            ]
            if "PK" not in {item.upper() for item in constraints}:
                constraints.append("PK")
            source_pk["constraints"] = constraints
            table.setdefault("columns", []).insert(0, source_pk)
    return normalize_erd_tables(repaired)


def _best_db_table_identifier(table: dict[str, Any]) -> str:
    """논리명과 대표 컬럼에서 근거가 있는 DB 테이블 ID를 결정합니다."""

    logical_name = str(
        table.get("entity_name")
        or table.get("table_logical_name")
        or table.get("logical_name")
        or ""
    ).strip()
    normalized_logical = logical_name
    for phrase in (
        "기본사항",
        "요구사항",
        "정보 관리",
        "정보관리",
        "고도화",
    ):
        normalized_logical = normalized_logical.replace(phrase, " ")
    normalized_logical = re.sub(r"\s+", " ", normalized_logical).strip()

    candidates: list[tuple[int, str]] = []

    def add(score: int, value: str) -> None:
        if valid_table_identifier(value):
            candidates.append((score, value))

    add(100, table_name(normalized_logical))
    add(80, table_name(logical_name))

    for column in table.get("columns", []):
        if not isinstance(column, dict):
            continue
        constraints = {str(item).upper() for item in column.get("constraints", [])}
        physical = _physical_column_name(column)
        logical = str(
            column.get("attribute_name")
            or column.get("logical_name")
            or column.get("column_logical_name")
            or ""
        )
        if _column_is_pk(column) or "PK" in constraints:
            stem = re.sub(r"_(?:sn|id)$", "", physical.lower())
            if stem not in {"", "data", "entity", "item", "info"}:
                add(95, f"tbl_{stem}")
            pk_logical = re.sub(
                r"(?:일련번호|식별번호|식별자|번호|ID|아이디)$",
                "",
                logical,
            ).strip()
            add(90, table_name(pk_logical))

    if not candidates:
        return ""
    return sorted(candidates, key=lambda item: (-item[0], len(item[1]), item[1]))[0][1]


def _column_is_pk(column: dict[str, Any]) -> bool:
    value = column.get("pk") or column.get("is_pk")
    if isinstance(value, str):
        return value.strip().upper() in {"Y", "YES", "TRUE", "1", "PK"}
    return bool(value)


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
                "column_logical_name": db_column_logical_name(
                    column.get("column_logical_name")
                    or column.get("attribute_name")
                    or column.get("logical_name"),
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
        "tablespace_name": str(item.get("tablespace_name") or tablespace_name(table_name)),
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
            if key == "constraint" and _looks_like_standard_evidence_constraint(value):
                continue
            merged[key] = value

    base_constraints = base_column.get("constraints") if isinstance(base_column.get("constraints"), list) else []
    candidate_constraints = candidate_column.get("constraints") if isinstance(candidate_column.get("constraints"), list) else []
    merged["constraints"] = [
        item
        for item in dict.fromkeys([*base_constraints, *candidate_constraints])
        if not _looks_like_standard_evidence_constraint(item)
    ]
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
    if explicit not in (None, "", []) and not _looks_like_standard_evidence_constraint(explicit):
        return str(explicit)
    constraints = column.get("constraints") if isinstance(column.get("constraints"), list) else []
    filtered = [
        str(item)
        for item in constraints
        if str(item).upper() not in {"PK", "FK", "INDEX", "IDX", "NOT NULL"}
        and not _looks_like_standard_evidence_constraint(item)
    ]
    return "; ".join(filtered)


def _looks_like_standard_evidence_constraint(value: Any) -> bool:
    text = re.sub(r"\s+", " ", str(value or "").strip().lstrip("\ufeff"))
    if not text:
        return False
    if re.search(
        r"(?:^|[\s\[\(])(?:공통표준(?:용어|단어|도메인)|standard[_ -]?(?:term|word|domain))[_\-\s]*\d*\s*[:：]",
        text,
        re.IGNORECASE,
    ):
        return True
    if re.search(r"\d+\s*자리\s*이내\s*문자(?:로)?\s*저장", text):
        return True
    if re.search(r"(?:Y/N|YN|코드|문자열?|숫자|날짜|일시|BOOLEAN|BOOL).{0,24}(?:형식|포맷|타입|도메인).{0,24}저장", text, re.IGNORECASE):
        return True
    if re.search(r"(?:형식|포맷|타입|도메인)(?:으로)?\s*저장", text):
        return True
    return False


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
