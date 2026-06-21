# 이미지 분석 Agent의 실행 진입점입니다.

from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable
import re
from typing import Any

from agents.image_analysis.processors import (
    analyze_images,
    build_description,
    build_image_request_message,
    build_ui_structure,
    enrich_interface_screens,
    match_creation_screens,
    match_update_screens,
    refine_screen_designs,
)
from config.settings import get_settings
from tools.llm.llm_client import LLMClient
from tools.llm.response_parser import parse_json_response
from tools.llm.send_api import send_parallel
from tools.result import ToolResult
from tools.search.search_router import search
from workflow.state import WorkflowState


class ImageAnalysisAgent:
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
            fallback_screens = match_creation_screens(requirements, analyses)
            query_specs = self._build_search_queries(fallback_screens, state, warnings)
            search_debug = self._search_contexts_parallel(query_specs, warnings)
            screens = self._match_creation_with_llm(requirements, analyses, search_debug, fallback_screens, warnings)
            source_items = requirements
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
            fallback_screens = match_update_screens(artifacts, analyses)
            query_specs = self._build_search_queries(fallback_screens, state, warnings)
            search_debug = self._search_contexts_parallel(query_specs, warnings)
            screens = self._match_update_with_llm(artifacts, analyses, search_debug, fallback_screens, warnings)
            source_items = artifacts
        else:
            return self._store(state, self._failed("IMAGE_ANALYSIS_INVALID_MODE", f"허용되지 않은 udt_yn입니다: {mode}"))

        screens = refine_screen_designs(
            screens,
            source_items,
            llm_client=self.llm_client,
            warnings=warnings,
            search_contexts=search_debug,
            max_workers=self.max_parallel_workers,
        )
        self._apply_descriptions(screens, search_debug, warnings)
        screens, marker_warnings = enrich_interface_screens(
            screens,
            output_dir=get_settings().temp_dir / "interface_numbered_images",
        )
        warnings.extend(marker_warnings)
        ui_structure = self._generate_ui_structure(screens, warnings)

        output: dict[str, Any] = {
            "status": "SUCCESS",
            "interface_image_analysis_json_list": screens,
            "ui_structure": ui_structure,
            "warnings": warnings,
            "errors": [],
        }
        if bool(state.get("etc", {}).get("debug")):
            output["debug"] = {
                "image_analysis_result_list": analyses,
                "rag_results": search_debug,
                "ui_structure": ui_structure,
            }
        return self._store(state, output)

    def _build_search_queries(
        self,
        screens: list[dict[str, Any]],
        state: WorkflowState,
        warnings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        settings = get_settings()
        fallback_specs = [
            {
                "screen_id": screen["screen_id"],
                "screen_name": screen["screen_name"],
                "ux_query": f"{screen['screen_name']} UI UX 가이드",
                "ux_filters": {
                    "domain": "interface",
                    "chunk_type": "uiux_guideline",
                    "keywords": _screen_keywords(screen),
                },
                "ux_collection": settings.alpled_reference_collection,
                "interface_query": f"{screen['screen_name']} 인터페이스 요구사항",
                "interface_filters": {
                    "project_sn": state.get("project_sn"),
                    "requirement_type": ["인터페이스", "인터페이스 요구사항"],
                    "keywords": _screen_keywords(screen),
                },
                "interface_collection": settings.alpled_reference_collection,
            }
            for screen in screens
        ]
        if self.llm_client is None or not screens:
            return fallback_specs

        requests = [
            {
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "이미지 분석 결과를 기준으로 화면별 RAG 검색 Query를 생성하세요. "
                            "JSON으로 ux_query, interface_query만 반환하세요."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"화면 정보: {screen}\n"
                            "1. UI/UX 가이드 검색 Query\n"
                            "2. 프로젝트 인터페이스 요구사항 검색 Query"
                        ),
                    },
                ]
            }
            for screen in screens
        ]
        result = send_parallel(
            requests,
            client=self.llm_client,
            max_workers=self.max_parallel_workers,
        )
        if not result["success"]:
            warnings.append({"code": "IMAGE_ANALYSIS_QUERY_BUILDER_FAILED", "message": result["error"]["message"]})
            return fallback_specs

        specs = []
        for index, llm_result in enumerate(result["data"]):
            spec = dict(fallback_specs[index])
            if llm_result and llm_result["success"]:
                parsed = parse_json_response(llm_result["data"])
                if parsed["success"] and isinstance(parsed["data"], dict):
                    spec["ux_query"] = str(parsed["data"].get("ux_query") or spec["ux_query"])
                    spec["interface_query"] = str(parsed["data"].get("interface_query") or spec["interface_query"])
                else:
                    warnings.append(
                        {
                            "code": "IMAGE_ANALYSIS_QUERY_BUILDER_FALLBACK",
                            "message": "검색 Query 생성 결과를 기본값으로 대체했습니다.",
                            "screen_id": spec["screen_id"],
                        }
                    )
            specs.append(spec)
        return specs

    def _search_contexts_parallel(
        self,
        query_specs: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        contexts = [
            {
                "screen_id": spec["screen_id"],
                "screen_name": spec["screen_name"],
                "ux_guides": [],
                "interface_requirements": [],
            }
            for spec in query_specs
        ]
        if not query_specs:
            return contexts

        future_map = {}
        with ThreadPoolExecutor(max_workers=self.max_parallel_workers) as executor:
            for index, spec in enumerate(query_specs):
                future_map[
                    executor.submit(
                        self._search,
                        spec["ux_query"],
                        spec["ux_filters"],
                        spec.get("ux_collection"),
                        warnings,
                    )
                ] = (index, "ux_guides")
                future_map[
                    executor.submit(
                        self._search,
                        spec["interface_query"],
                        spec["interface_filters"],
                        spec.get("interface_collection"),
                        warnings,
                    )
                ] = (index, "interface_requirements")

            for future in as_completed(future_map):
                index, key = future_map[future]
                try:
                    contexts[index][key] = future.result()
                except Exception as exc:
                    warnings.append(
                        {
                            "code": "IMAGE_ANALYSIS_RAG_EXCEPTION",
                            "message": str(exc),
                            "screen_id": contexts[index]["screen_id"],
                            "target": key,
                        }
                    )
        return contexts

    def _search(
        self,
        query: str,
        filters: dict[str, Any],
        collection: str | None,
        warnings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result = self.search_tool(query, search_targets="RAG", filters=filters, collection=collection)
        if result["success"]:
            return result["data"]["normalized_results"]
        warnings.append({"code": "IMAGE_ANALYSIS_RAG_FAILED", "message": result["error"]["message"], "query": query})
        return []

    def _match_creation_with_llm(
        self,
        requirements: list[dict[str, Any]],
        analyses: list[dict[str, Any]],
        search_contexts: list[dict[str, Any]],
        fallback_screens: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if self.llm_client is None:
            return fallback_screens
        return self._match_with_llm(
            system_prompt=(
                "요구사항, 이미지 분석 결과, UI/UX 가이드, 인터페이스 요구사항을 기준으로 "
                "요구사항과 이미지를 매칭하세요. JSON으로 interface_image_analysis_json_list를 반환하세요."
            ),
            user_payload={
                "integrated_requirement_json_list": requirements,
                "image_analysis_result_list": analyses,
                "rag_results": search_contexts,
                "fallback_screens": fallback_screens,
            },
            fallback_screens=fallback_screens,
            warnings=warnings,
        )

    def _match_update_with_llm(
        self,
        artifacts: list[dict[str, Any]],
        analyses: list[dict[str, Any]],
        search_contexts: list[dict[str, Any]],
        fallback_screens: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if self.llm_client is None:
            return fallback_screens
        return self._match_with_llm(
            system_prompt=(
                "수정용 산출물 JSON과 이미지 분석 결과를 매칭하고 화면별 이미지 유지, 수정, 추가, 삭제 "
                "필요 여부를 판단하세요. JSON으로 interface_image_analysis_json_list를 반환하세요."
            ),
            user_payload={
                "integrated_artifact_json_list": artifacts,
                "image_analysis_result_list": analyses,
                "rag_results": search_contexts,
                "fallback_screens": fallback_screens,
            },
            fallback_screens=fallback_screens,
            warnings=warnings,
        )

    def _match_with_llm(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        fallback_screens: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        assert self.llm_client is not None
        result = self.llm_client.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": str(user_payload)},
            ]
        )
        if not result["success"]:
            warnings.append({"code": "IMAGE_ANALYSIS_MATCH_LLM_FAILED", "message": result["error"]["message"]})
            return fallback_screens
        parsed = parse_json_response(result["data"])
        if not parsed["success"]:
            warnings.append({"code": "IMAGE_ANALYSIS_MATCH_LLM_FALLBACK", "message": parsed["error"]["message"]})
            return fallback_screens

        candidate = parsed["data"]
        if isinstance(candidate, dict):
            candidate = candidate.get("interface_image_analysis_json_list") or candidate.get("screens")
        if not isinstance(candidate, list) or not candidate:
            return fallback_screens
        return _merge_llm_screens(candidate, fallback_screens)

    def _apply_descriptions(
        self,
        screens: list[dict[str, Any]],
        search_contexts: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> None:
        context_by_id = {context["screen_id"]: context for context in search_contexts}
        fallback_descriptions = [
            build_description(
                screen,
                ux_guides=context_by_id.get(screen["screen_id"], {}).get("ux_guides", []),
                interface_requirements=context_by_id.get(screen["screen_id"], {}).get("interface_requirements", []),
            )
            for screen in screens
        ]
        if self.llm_client is None or not screens:
            for screen, description in zip(screens, fallback_descriptions):
                screen["description"] = description
                screen["image_request_message"] = build_image_request_message(screen)
            return

        requests = [
            {
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "화면별 description과 이미지 보완 요청 문구를 생성하세요. "
                            "JSON으로 description만 반환하세요."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"screen: {screen}\n"
                            f"rag_context: {context_by_id.get(screen['screen_id'], {})}\n"
                            f"fallback_description: {fallback_descriptions[index]}"
                        ),
                    },
                ]
            }
            for index, screen in enumerate(screens)
        ]
        result = send_parallel(
            requests,
            client=self.llm_client,
            max_workers=self.max_parallel_workers,
        )
        if not result["success"]:
            warnings.append({"code": "IMAGE_ANALYSIS_DESCRIPTION_LLM_FAILED", "message": result["error"]["message"]})
            for screen, description in zip(screens, fallback_descriptions):
                screen["description"] = description
                screen["image_request_message"] = build_image_request_message(screen)
            return

        for index, (screen, llm_result) in enumerate(zip(screens, result["data"])):
            description = fallback_descriptions[index]
            if llm_result and llm_result["success"]:
                parsed = parse_json_response(llm_result["data"])
                if parsed["success"] and isinstance(parsed["data"], dict):
                    description = str(parsed["data"].get("description") or description)
            screen["description"] = description
            screen["image_request_message"] = build_image_request_message(screen)

    def _generate_ui_structure(
        self,
        screens: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        fallback = build_ui_structure(screens)
        if self.llm_client is None or not screens:
            return fallback
        result = self.llm_client.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "사용자 인터페이스 구조도를 Level1~Level4 JSON 배열로 생성하세요. "
                        "각 항목은 level1, level2, level3, level4를 가져야 합니다."
                    ),
                },
                {"role": "user", "content": str({"screens": screens, "fallback": fallback})},
            ]
        )
        if not result["success"]:
            warnings.append({"code": "IMAGE_ANALYSIS_UI_STRUCTURE_FAILED", "message": result["error"]["message"]})
            return fallback
        parsed = parse_json_response(result["data"])
        if not parsed["success"]:
            warnings.append({"code": "IMAGE_ANALYSIS_UI_STRUCTURE_FALLBACK", "message": parsed["error"]["message"]})
            return fallback
        rows = parsed["data"]
        if isinstance(rows, dict):
            rows = rows.get("ui_structure") or rows.get("items") or []
        if not isinstance(rows, list):
            return fallback
        normalized = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            normalized.append(
                _normalize_ui_structure_levels({
                    "level1": str(item.get("level1") or ""),
                    "level2": str(item.get("level2") or ""),
                    "level3": str(item.get("level3") or ""),
                    "level4": str(item.get("level4") or ""),
                })
            )
        return normalized or fallback

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


def _normalize_ui_structure_levels(row: dict[str, str]) -> dict[str, str]:
    if row.get("level1") == "업무 화면" and row.get("level2") and not row.get("level3") and not row.get("level4"):
        module_name, detail_name = _screen_menu_levels(row["level2"])
        row = {
            "level1": "AI 통합 플랫폼",
            "level2": module_name,
            "level3": "업무 화면",
            "level4": detail_name,
        }
    return _dedupe_ui_structure_levels(row)


def _dedupe_ui_structure_levels(row: dict[str, str]) -> dict[str, str]:
    seen: set[str] = set()
    cleaned = {}
    for key in ("level1", "level2", "level3", "level4"):
        value = str(row.get(key) or "").strip()
        if value and value in seen:
            value = ""
        if value:
            seen.add(value)
        cleaned[key] = value
    return cleaned


def _screen_menu_levels(screen_name: str) -> tuple[str, str]:
    name = re.sub(r"^\d{1,3}_", "", str(screen_name or "").strip())
    parts = [part for part in name.split("_") if part]
    if len(parts) >= 2:
        return " ".join(parts[:-1]), parts[-1]
    return name or "업무", name or "화면"


def _screen_keywords(screen: dict[str, Any]) -> list[str]:
    analysis = screen.get("analysis") or {}
    raw_values = [
        screen.get("screen_name"),
        analysis.get("purpose"),
        *(analysis.get("input_fields") or []),
        *(analysis.get("buttons") or []),
        *(analysis.get("user_actions") or []),
    ]
    return [str(value) for value in raw_values if value]


def _merge_llm_screens(
    llm_screens: list[dict[str, Any]],
    fallback_screens: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    fallback_by_id = {screen["screen_id"]: screen for screen in fallback_screens}
    fallback_by_image_path = {
        str(screen.get("image_path")): screen
        for screen in fallback_screens
        if screen.get("image_path")
    }
    fallback_by_name = {
        str(screen.get("screen_name")): screen
        for screen in fallback_screens
        if screen.get("screen_name")
    }
    merged: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for index, llm_screen in enumerate(llm_screens):
        if not isinstance(llm_screen, dict):
            continue
        screen_id = str(llm_screen.get("screen_id") or f"SCR-{index + 1:03d}")
        fallback_base = (
            fallback_by_id.get(screen_id)
            or fallback_by_image_path.get(str(llm_screen.get("image_path")))
            or fallback_by_name.get(str(llm_screen.get("screen_name")))
            or {}
        )
        fallback_base_id = str(fallback_base.get("screen_id") or "")
        base = dict(fallback_base)
        base_analysis = base.get("analysis") if isinstance(base.get("analysis"), dict) else {}
        llm_analysis = llm_screen.get("analysis") if isinstance(llm_screen.get("analysis"), dict) else {}
        base.update(llm_screen)
        base["analysis"] = {**base_analysis, **llm_analysis}
        base.setdefault("screen_id", screen_id)
        base.setdefault("screen_name", str(base.get("screen_name") or f"화면 {index + 1}"))
        base.setdefault("matched_requirement_ids", [])
        base.setdefault("match_status", base.get("image_status") or "MATCHED")
        base.setdefault("image_status", base["match_status"])
        base.setdefault("analysis", {})
        merged.append(base)
        used_ids.add(str(base["screen_id"]))
        if fallback_base_id:
            used_ids.add(fallback_base_id)

    for fallback in fallback_screens:
        if fallback["screen_id"] not in used_ids:
            merged.append(fallback)
    return merged
