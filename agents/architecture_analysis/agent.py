# 아키텍처 설계서 생성 및 수정 Agent의 실행 진입점입니다.

from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable
from typing import Any

from agents.architecture_analysis.processors import (
    apply_architecture_changes,
    build_architecture_document,
    build_architecture_drivers,
    build_architecture_rag_queries,
    build_architecture_structure,
    build_component_candidates,
    build_component_relations,
    build_deployment_environment,
    build_layers,
    extract_existing_structure,
    filter_architecture_requirements,
    normalize_components,
    normalize_relations,
)
from config.settings import get_settings
from tools.llm.llm_client import LLMClient
from tools.llm.response_parser import parse_json_response
from tools.llm.send_api import send_parallel
from tools.result import ToolResult
from tools.search.search_router import search
from workflow.state import WorkflowState


class ArchitectureAnalysisAgent:
    def __init__(
        self,
        *,
        llm_client: LLMClient | None = None,
        search_tool: Callable[..., ToolResult] = search,
        architecture_config_repository: Any | None = None,
        max_parallel_workers: int = 4,
    ) -> None:
        self.llm_client = llm_client
        self.search_tool = search_tool
        self.architecture_config_repository = architecture_config_repository
        self.max_parallel_workers = max(1, max_parallel_workers)

    def execute(self, state: WorkflowState) -> dict[str, Any]:
        docs_cd = str(state.get("docs_cd", "")).upper()
        mode = str(state.get("udt_yn", "")).upper()
        if docs_cd != "ARCH":
            return self._store(state, self._failed("ARCHITECTURE_INVALID_DOCS_CD", "architecture_analysis_agent는 ARCH 산출물에서만 실행할 수 있습니다."))

        document_merge = state.get("agent_outputs", {}).get("document_merge_agent", {})
        config, config_warnings = self._load_architecture_config(state)
        if mode == "N":
            output = self._create(document_merge, state, config, config_warnings)
        elif mode == "Y":
            output = self._update(document_merge, state, config, config_warnings)
        else:
            output = self._failed("ARCHITECTURE_INVALID_MODE", f"허용되지 않은 udt_yn입니다: {mode}")
        return self._store(state, output)

    def _create(
        self,
        document_merge: dict[str, Any],
        state: WorkflowState,
        architecture_config: dict[str, Any],
        warnings: list[dict[str, Any]],
    ) -> dict[str, Any]:
        requirements = document_merge.get("integrated_requirement_json_list")
        if not isinstance(requirements, list) or not requirements:
            return self._failed("ARCH_REQUIREMENT_MISSING", "integrated_requirement_json_list가 필요합니다.")

        selected_requirements = filter_architecture_requirements(requirements)
        query_specs = self._build_rag_queries(selected_requirements, state, warnings)
        rag_results = self._search_rag_parallel(query_specs, warnings)
        drivers = self._build_drivers(selected_requirements, architecture_config, rag_results, warnings)
        components = self._build_components(selected_requirements, architecture_config, drivers, warnings)
        relations = self._build_relations(components, architecture_config, warnings)
        layers = self._build_layers(components, relations, warnings)
        return self._success(
            state,
            components=components,
            relations=relations,
            layers=layers,
            drivers=drivers,
            architecture_config=architecture_config,
            rag_results=rag_results,
            warnings=warnings,
            debug={
                "rag_query_specs": query_specs,
                "rag_results": rag_results,
                "selected_requirements": selected_requirements,
            },
        )

    def _update(
        self,
        document_merge: dict[str, Any],
        state: WorkflowState,
        architecture_config: dict[str, Any],
        warnings: list[dict[str, Any]],
    ) -> dict[str, Any]:
        existing = document_merge.get("existing_output_raw_json")
        changes = document_merge.get("meeting_change_items")
        if not isinstance(existing, dict) or not existing:
            return self._failed("ARCH_EXISTING_OUTPUT_MISSING", "existing_output_raw_json이 필요합니다.")
        if not isinstance(changes, list):
            return self._failed("ARCH_MEETING_CHANGE_MISSING", "meeting_change_items가 필요합니다.")

        existing_structure = extract_existing_structure(existing)
        components = normalize_components(existing_structure.get("components") or [])
        if not components:
            components = build_component_candidates([], architecture_config, [])
        self._analyze_change_impacts(changes, warnings)
        components = apply_architecture_changes(components, changes)
        relations = normalize_relations(existing_structure.get("relations") or existing_structure.get("edges") or [], components)
        if not relations:
            relations = build_component_relations(components)
        relations = self._build_relations(components, architecture_config, warnings, fallback=relations)
        layers = self._build_layers(components, relations, warnings)
        drivers = build_architecture_drivers([], architecture_config, [])
        return self._success(
            state,
            components=components,
            relations=relations,
            layers=layers,
            drivers=drivers,
            architecture_config=architecture_config,
            rag_results=[],
            warnings=warnings,
            meeting_change_items=changes,
            debug={
                "existing_output_raw_json": existing,
                "meeting_change_items": changes,
            },
        )

    def _load_architecture_config(
        self,
        state: WorkflowState,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        config = state.get("etc", {}).get("architecture_config")
        if isinstance(config, dict) and config:
            return config, []

        if self.architecture_config_repository is not None:
            try:
                loaded = self.architecture_config_repository.find_by_project_sn(int(state.get("project_sn") or 0))
                if isinstance(loaded, dict):
                    return loaded, []
                if loaded is not None and hasattr(loaded, "__dict__"):
                    return {key: value for key, value in vars(loaded).items() if not key.startswith("_")}, []
            except NotImplementedError:
                return {}, [{"code": "ARCH_CONFIG_REPOSITORY_TODO", "message": "architecture_config Repository가 아직 구현되지 않았습니다."}]
            except Exception as exc:
                return {}, [{"code": "ARCH_CONFIG_LOAD_FAILED", "message": str(exc)}]

        return {}, [{"code": "ARCH_CONFIG_MISSING", "message": "architecture_config가 없어 기본 아키텍처 설정으로 생성합니다."}]

    def _build_rag_queries(
        self,
        requirements: list[dict[str, Any]],
        state: WorkflowState,
        warnings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        fallback = build_architecture_rag_queries(requirements, state.get("project_sn"))
        if self.llm_client is None:
            return fallback
        result = send_parallel(
            [
                {
                    "messages": [
                        {
                            "role": "system",
                            "content": "아키텍처 설계에 필요한 비기능 요구사항 RAG 검색 Query를 JSON으로 생성하세요.",
                        },
                        {"role": "user", "content": str(spec)},
                    ]
                }
                for spec in fallback
            ],
            client=self.llm_client,
            max_workers=self.max_parallel_workers,
        )
        if not result["success"]:
            warnings.append({"code": "ARCH_RAG_QUERY_LLM_FAILED", "message": result["error"]["message"]})
            return fallback

        specs = []
        for index, response in enumerate(result["data"]):
            spec = dict(fallback[index])
            parsed = parse_json_response(response["data"]) if response and response["success"] else None
            if parsed and parsed["success"] and isinstance(parsed["data"], dict):
                spec["query"] = str(parsed["data"].get("query") or spec["query"])
                if isinstance(parsed["data"].get("filters"), dict):
                    spec["filters"] = {**spec["filters"], **parsed["data"]["filters"]}
            else:
                warnings.append({"code": "ARCH_RAG_QUERY_FALLBACK", "message": f"RAG query {index + 1}을 기본값으로 대체했습니다."})
            specs.append(spec)
        return specs

    def _search_rag_parallel(
        self,
        query_specs: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        settings = get_settings()
        with ThreadPoolExecutor(max_workers=self.max_parallel_workers) as executor:
            future_map = {
                executor.submit(
                    self.search_tool,
                    {
                        "project_sn": spec["filters"].get("project_sn"),
                        "docs_cd": "ARCH",
                        "agent_name": "architecture_analysis_agent",
                        "search_intent": spec["search_intent"],
                        "query": spec["query"],
                        "search_targets": "RAG",
                        "filters": spec["filters"],
                        "top_k": 5,
                        "collection": settings.alpled_reference_collection,
                    },
                ): spec
                for spec in query_specs
            }
            for future in as_completed(future_map):
                spec = future_map[future]
                try:
                    result = future.result()
                except Exception as exc:
                    warnings.append({"code": "ARCH_RAG_EXCEPTION", "message": str(exc), "query": spec["query"]})
                    continue
                if result["success"]:
                    normalized = result["data"].get("normalized_results", [])
                    results.append(
                        {
                            "search_intent": spec["search_intent"],
                            "query": spec["query"],
                            "normalized_results": _dedupe_results(normalized),
                        }
                    )
                else:
                    warnings.append({"code": "ARCH_RAG_FAILED", "message": result["error"]["message"], "query": spec["query"]})
        return results

    def _build_drivers(
        self,
        requirements: list[dict[str, Any]],
        architecture_config: dict[str, Any],
        rag_results: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        fallback = build_architecture_drivers(requirements, architecture_config, rag_results)
        value = self._llm_dict(
            "요구사항, architecture_config, 비기능 RAG 결과를 분석하여 아키텍처 설계 Driver를 JSON으로 반환하세요.",
            {"requirements": requirements, "architecture_config": architecture_config, "rag_results": rag_results},
            warnings,
            "ARCH_DRIVER_LLM_FAILED",
        )
        drivers = value.get("drivers") if isinstance(value, dict) else None
        return drivers if isinstance(drivers, list) and drivers else fallback

    def _build_components(
        self,
        requirements: list[dict[str, Any]],
        architecture_config: dict[str, Any],
        drivers: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        fallback = build_component_candidates(requirements, architecture_config, drivers)
        value = self._llm_dict(
            "아키텍처 컴포넌트 후보를 생성하세요. JSON으로 components를 반환하세요.",
            {"requirements": requirements, "architecture_config": architecture_config, "drivers": drivers},
            warnings,
            "ARCH_COMPONENT_LLM_FAILED",
        )
        components = value.get("components") if isinstance(value, dict) else None
        return normalize_components(components if isinstance(components, list) and components else fallback)

    def _build_relations(
        self,
        components: list[dict[str, Any]],
        architecture_config: dict[str, Any],
        warnings: list[dict[str, Any]],
        fallback: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        fallback = fallback or build_component_relations(components)
        value = self._llm_dict(
            "컴포넌트 간 관계를 설계하세요. JSON으로 relations를 반환하세요.",
            {"components": components, "architecture_config": architecture_config, "fallback_relations": fallback},
            warnings,
            "ARCH_RELATION_LLM_FAILED",
        )
        relations = value.get("relations") if isinstance(value, dict) else None
        return normalize_relations(relations if isinstance(relations, list) and relations else fallback, components)

    def _build_layers(
        self,
        components: list[dict[str, Any]],
        relations: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        fallback = build_layers(components)
        value = self._llm_dict(
            "아키텍처 계층 구조를 설계하세요. JSON으로 layers를 반환하세요.",
            {"components": components, "relations": relations, "fallback_layers": fallback},
            warnings,
            "ARCH_LAYER_LLM_FAILED",
        )
        layers = value.get("layers") if isinstance(value, dict) else None
        return layers if isinstance(layers, list) and layers else fallback

    def _analyze_change_impacts(
        self,
        changes: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> None:
        if self.llm_client is None or not changes:
            return
        result = send_parallel(
            [
                {
                    "messages": [
                        {"role": "system", "content": "회의록 변경사항별 아키텍처 영향 분석 결과를 JSON으로 반환하세요."},
                        {"role": "user", "content": str(change)},
                    ]
                }
                for change in changes
            ],
            client=self.llm_client,
            max_workers=self.max_parallel_workers,
        )
        if not result["success"]:
            warnings.append({"code": "ARCH_CHANGE_IMPACT_LLM_FAILED", "message": result["error"]["message"]})

    def _llm_dict(
        self,
        instruction: str,
        payload: dict[str, Any],
        warnings: list[dict[str, Any]],
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
            warnings.append({"code": warning_code, "message": result["error"]["message"]})
            return {}
        parsed = parse_json_response(result["data"])
        if parsed["success"] and isinstance(parsed["data"], dict):
            return parsed["data"]
        warnings.append({"code": warning_code, "message": "LLM 응답을 JSON 객체로 해석하지 못해 기본값을 사용합니다."})
        return {}

    def _success(
        self,
        state: WorkflowState,
        *,
        components: list[dict[str, Any]],
        relations: list[dict[str, Any]],
        layers: list[dict[str, Any]],
        drivers: list[dict[str, Any]],
        architecture_config: dict[str, Any],
        rag_results: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
        meeting_change_items: list[dict[str, Any]] | None = None,
        debug: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        deployment_environment = build_deployment_environment(architecture_config)
        structure = build_architecture_structure(
            components=components,
            relations=relations,
            layers=layers,
            deployment_environment=deployment_environment,
            drivers=drivers,
            architecture_config=architecture_config,
        )
        document = build_architecture_document(
            structure=structure,
            rag_results=rag_results,
            meeting_change_items=meeting_change_items,
        )
        output: dict[str, Any] = {
            "status": "SUCCESS",
            "architecture_structure_json": structure,
            "architecture_document_json": document,
            "warnings": warnings,
            "errors": [],
        }
        if bool(state.get("etc", {}).get("debug")):
            output["debug"] = debug or {}
        return output

    @staticmethod
    def _store(state: WorkflowState, output: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("agent_outputs", {})["architecture_analysis_agent"] = output
        return output

    @staticmethod
    def _failed(code: str, message: str) -> dict[str, Any]:
        return {
            "status": "FAILED",
            "failure_type": code,
            "warnings": [],
            "errors": [{"code": code, "message": message}],
        }


def _dedupe_results(results: list[Any]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
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
