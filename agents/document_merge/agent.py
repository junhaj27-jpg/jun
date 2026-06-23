# 기존 산출물과 회의록을 분석하고 통합하는 Agent의 실행 진입점입니다.

from collections.abc import Callable
import json
from typing import Any

from agents.document_merge.processors import analyze_meetings, artifact_items, merge_items, parse_artifact
from tools.llm.llm_client import LLMClient
from tools.llm.response_parser import parse_json_response
from tools.llm.send_api import send_parallel
from tools.parser.db_design_docx_parser import parse_db_design_docx
from tools.parser.erd_docx_parser import parse_erd_docx
from tools.parser.image_extractor import extract_images
from tools.parser.rfp_rule_parser import parse_rfp_requirements
from tools.result import ToolResult
from tools.search.search_router import search
from tools.vector.embedding_writer import write_non_functional_requirements
from workflow.state import WorkflowState


class DocumentMergeAgent:
    # reference_type별 구조화 프롬프트. 미정의 타입(ERD 등)은 기존 범용 프롬프트를 사용함.
    _REFERENCE_SCHEMA_PROMPTS: dict[str, str] = {
        "INTERFACE": (
            "인터페이스(화면) 설계서 텍스트를 후속 시험 시나리오 생성 Agent가 사용할 "
            "JSON 배열로 구조화하세요. 각 항목은 다음 키를 포함해야 합니다: "
            "screen_id(화면 식별자, 문서에 명시된 식별자가 없으면 'SCR-' + 일련번호로 생성), "
            "screen_name(화면명), "
            "description(화면 목적/주요 기능 한 문장 요약), "
            "matched_requirement_ids(이 화면과 연관된 요구사항 ID 문자열 배열, 알 수 없으면 빈 배열). "
            "최상위는 {\"reference_interface_json_list\": [...]} 형식의 JSON 객체 하나만 반환하세요. "
            "설명이나 마크다운 코드블록 없이 JSON만 응답하세요."
        ),
    }

    def __init__(
        self,
        *,
        llm_client: LLMClient | None = None,
        rfp_parser: Callable[[str], ToolResult] = parse_rfp_requirements,
        search_tool: Callable[..., ToolResult] = search,
        embedding_writer: Callable[..., ToolResult] = write_non_functional_requirements,
        max_parallel_workers: int = 4,
    ) -> None:
        self.llm_client = llm_client
        self.rfp_parser = rfp_parser
        self.search_tool = search_tool
        self.embedding_writer = embedding_writer
        self.max_parallel_workers = max_parallel_workers

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
        parsed_data = parsed["data"]
        requirements = list(parsed_data.get("requirements") or parsed_data.get("functional_requirements", []))
        non_functional_requirements = list(
            parsed_data.get("non_functional_requirements")
            or _non_functional_items(requirements)
        )
        changes, warnings = self._meeting_changes(state)
        changes = self._enrich_changes_with_search(changes, warnings)
        changes = self._merge_search_results_with_llm(changes, warnings)
        integrated = self._apply_changes_to_items(requirements, changes, warnings)
        self._write_non_functional_embeddings(non_functional_requirements, state, warnings)
        return self._success(
            warnings=warnings,
            integrated_requirement_json_list=integrated,
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
        changes = self._merge_search_results_with_llm(changes, warnings)
        base_items = self._filter_requirements_for_docs(
            docs_cd,
            artifact_items(parsed["data"]),
        )
        integrated = self._apply_changes_to_items(base_items, changes, warnings)
        output = self._success(
            warnings=warnings,
            integrated_requirement_json_list=integrated,
        )
        if docs_cd == "DB":
            reference = self._parse_reference(state.get("erd_file_path"), "ERD", warnings)
            if not reference["success"]:
                return reference["output"]
            output["reference_erd_json_list"] = reference["items"]
        elif docs_cd == "TS":
            reference = self._parse_reference(state.get("interface_file_path"), "INTERFACE", warnings)
            if not reference["success"]:
                return reference["output"]
            output["reference_interface_json_list"] = reference["items"]
        return output

    def _update_artifact(self, state: WorkflowState, docs_cd: str) -> dict[str, Any]:
        existing_path = state.get("existing_output_path")
        requested_path = state.get("requested_output_path")
        meeting_paths = list(state.get("input_file_paths") or [])
        if not existing_path:
            return self._failed("EXISTING_OUTPUT_MISSING", "existing_output_path가 필요합니다.")
        if not meeting_paths:
            return self._failed("MEETING_FILE_MISSING", "수정 모드에는 회의록 파일이 필요합니다.")
        parsed = self._parse_existing_artifact(existing_path, docs_cd)
        if not parsed["success"]:
            return self._tool_failed("EXISTING_OUTPUT_PARSE_FAILED", parsed)
        image_result = extract_images(existing_path)
        image_paths = image_result["data"]["image_paths"] if image_result["success"] else []
        changes, warnings = self._meeting_changes(state)
        changes = self._enrich_changes_with_search(changes, warnings)
        changes = self._merge_search_results_with_llm(changes, warnings)
        raw_json = parsed["data"].get("raw_json", parsed["data"])
        if docs_cd in {"ERD", "DB", "ARCH"}:
            requested_raw_json = None
            if requested_path:
                requested_parsed = self._parse_existing_artifact(
                    str(requested_path),
                    docs_cd,
                )
                if not requested_parsed["success"]:
                    return self._tool_failed(
                        "REQUESTED_OUTPUT_PARSE_FAILED",
                        requested_parsed,
                    )
                requested_raw_json = requested_parsed["data"].get(
                    "raw_json",
                    requested_parsed["data"],
                )
            return self._success(
                warnings=warnings,
                existing_output_raw_json=raw_json,
                requested_output_raw_json=requested_raw_json,
                meeting_change_items=changes,
                existing_output_image_paths=image_paths,
            )
        return self._success(
            warnings=warnings,
            integrated_artifact_json_list=self._apply_changes_to_items(
                artifact_items(raw_json),
                changes,
                warnings,
            ),
            existing_output_image_paths=image_paths,
        )

    def _parse_existing_artifact(self, existing_path: str, docs_cd: str) -> ToolResult:
        if docs_cd == "ERD" and str(existing_path).lower().endswith(".docx"):
            parsed_erd = parse_erd_docx(str(existing_path))
            if parsed_erd["success"]:
                return parsed_erd
        if docs_cd == "DB" and str(existing_path).lower().endswith(".docx"):
            parsed_db = parse_db_design_docx(str(existing_path))
            if parsed_db["success"] and parsed_db["data"].get("tables"):
                return parsed_db
        return parse_artifact(existing_path)

    def _meeting_changes(self, state: WorkflowState) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        excluded_paths = {
            str(path)
            for path in (
                state.get("base_rfp_path"),
                state.get("base_requirement_json_path"),
                state.get("erd_file_path"),
                state.get("interface_file_path"),
                state.get("existing_output_path"),
                state.get("requested_output_path"),
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
            docs_cd=str(state.get("docs_cd") or ""),
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

    def _parse_reference(
        self,
        path: str | None,
        reference_type: str,
        warnings: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not path:
            return {
                "success": False,
                "output": self._failed(
                    f"REFERENCE_{reference_type}_MISSING",
                    f"{reference_type} 참조 파일 경로가 필요합니다.",
                ),
            }
        if reference_type == "ERD" and str(path).lower().endswith(".docx"):
            parsed_erd = parse_erd_docx(str(path))
            if not parsed_erd["success"]:
                return {
                    "success": False,
                    "output": self._tool_failed("REFERENCE_ERD_PARSE_FAILED", parsed_erd),
                }
            return {
                "success": True,
                "items": parsed_erd["data"].get("tables", []),
            }
        parsed = parse_artifact(path)
        if not parsed["success"]:
            return {
                "success": False,
                "output": self._tool_failed(
                    f"REFERENCE_{reference_type}_PARSE_FAILED", parsed
                ),
            }
        items = artifact_items(parsed["data"])
        if (
            reference_type == "INTERFACE"
            and items
            and all(isinstance(item, dict) for item in items)
        ):
            # INTERFACE가 (export_node에서 새로 저장하는) JSON 경로로 들어오면 image_analysis_agent가
            # 이미 screen_id/screen_name/description/matched_requirement_ids를 갖춰 만들어둔 상태라
            # LLM 재구조화가 불필요함. docx 폴백(평문 텍스트, dict 아님)일 때만 아래 LLM 경로를 탄다.
            # ERD 등 다른 reference_type은 기존 동작을 그대로 유지(_structure_reference_with_llm 미변경).
            return {"success": True, "items": items}
        return {
            "success": True,
            "items": self._structure_reference_with_llm(
                items,
                reference_type,
                warnings,
            ),
        }

    def _apply_changes_to_items(
        self,
        base_items: list[Any],
        changes: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> list[Any]:
        if not changes:
            return base_items
        if self.llm_client is None:
            return merge_items(base_items, changes)

        update_changes = [
            change
            for change in changes
            if str(change.get("change_type") or change.get("operation") or "UPDATE").upper()
            != "ADD"
        ]
        add_changes = [
            change
            for change in changes
            if str(change.get("change_type") or change.get("operation") or "").upper() == "ADD"
        ]
        requests = [
            {
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "기존 item과 회의록 변경사항을 비교해 JSON으로 반환하세요. "
                            "형식: {\"change_type\":\"NONE|UPDATE|DELETE\", \"item\": {...}}"
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"item": item, "meeting_change_items": update_changes},
                            ensure_ascii=False,
                        ),
                    },
                ]
            }
            for item in base_items
        ]
        parallel = send_parallel(
            requests,
            client=self.llm_client,
            max_workers=self.max_parallel_workers,
        )
        if not parallel["success"]:
            warnings.append({"code": "DOCUMENT_MERGE_PARALLEL_LLM_FAILED", "message": parallel["error"]["message"]})
            return merge_items(base_items, changes)

        reduced_changes: list[dict[str, Any]] = []
        for index, item_result in enumerate(parallel["data"]):
            if not item_result or not item_result["success"]:
                continue
            parsed = parse_json_response(item_result["data"])
            if not parsed["success"] or not isinstance(parsed["data"], dict):
                continue
            change_type = str(parsed["data"].get("change_type") or "NONE").upper()
            if change_type == "NONE":
                continue
            reduced_changes.append(
                {
                    "change_type": change_type,
                    "target_id": self._item_id(base_items[index]),
                    "item": parsed["data"].get("item", base_items[index]),
                }
            )
        return merge_items(base_items, [*reduced_changes, *add_changes])

    def _merge_search_results_with_llm(
        self,
        changes: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        searchable = [change for change in changes if change.get("search_results")]
        if not searchable or self.llm_client is None:
            return changes
        requests = [
            {
                "messages": [
                    {
                        "role": "system",
                        "content": "회의록 변경사항과 검색 결과를 병합해 보강된 change item JSON을 반환하세요.",
                    },
                    {"role": "user", "content": json.dumps(change, ensure_ascii=False)},
                ]
            }
            for change in searchable
        ]
        parallel = send_parallel(
            requests,
            client=self.llm_client,
            max_workers=self.max_parallel_workers,
        )
        if not parallel["success"]:
            warnings.append({"code": "DOCUMENT_MERGE_SEARCH_LLM_FAILED", "message": parallel["error"]["message"]})
            return changes

        by_id = {id(change): change for change in changes}
        for change, item_result in zip(searchable, parallel["data"], strict=False):
            if not item_result or not item_result["success"]:
                continue
            parsed = parse_json_response(item_result["data"])
            if parsed["success"] and isinstance(parsed["data"], dict):
                by_id[id(change)] = {**change, **parsed["data"]}
        return [by_id[id(change)] for change in changes]

    def _structure_reference_with_llm(
        self,
        items: list[Any],
        reference_type: str,
        warnings: list[dict[str, Any]] | None = None,
    ) -> list[Any]:
        warnings = warnings if warnings is not None else []
        if self.llm_client is None or not items:
            return items

        system_prompt = self._REFERENCE_SCHEMA_PROMPTS.get(
            reference_type,
            f"{reference_type} 참조 문서를 후속 Agent가 사용할 JSON List로 구조화하세요.",
        )
        result = self.llm_client.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(items, ensure_ascii=False)},
            ]
        )
        if not result["success"]:
            warnings.append(
                {
                    "code": f"REFERENCE_{reference_type}_STRUCTURING_LLM_FAILED",
                    "message": (
                        f"{reference_type} 참조 문서 구조화 LLM 호출에 실패하여 "
                        "원본 텍스트를 그대로 사용합니다."
                    ),
                }
            )
            return items

        parsed = parse_json_response(result["data"])
        if not parsed["success"]:
            warnings.append(
                {
                    "code": f"REFERENCE_{reference_type}_STRUCTURING_PARSE_FAILED",
                    "message": (
                        f"{reference_type} 참조 문서 구조화 응답 파싱에 실패하여 "
                        "원본 텍스트를 그대로 사용합니다."
                    ),
                }
            )
            return items

        value = parsed["data"]
        if isinstance(value, dict):
            value = (
                value.get("items")
                or value.get("reference_items")
                or value.get("reference_erd_json_list")
                or value.get("reference_interface_json_list")
            )
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            warnings.append(
                {
                    "code": f"REFERENCE_{reference_type}_STRUCTURING_INVALID_SHAPE",
                    "message": (
                        f"{reference_type} 참조 문서 구조화 결과가 JSON 객체 배열 형식이 아니어서 "
                        "원본 텍스트를 그대로 사용합니다."
                    ),
                }
            )
            return items
        return value

    def _write_non_functional_embeddings(
        self,
        requirements: list[Any],
        state: WorkflowState,
        warnings: list[dict[str, Any]],
    ) -> None:
        dict_items = [item for item in requirements if isinstance(item, dict)]
        result = self.embedding_writer(
            dict_items,
            project_sn=state.get("project_sn"),
            source_path=state.get("base_rfp_path") or state.get("base_requirement_json_path"),
        )
        if not result["success"]:
            warnings.append({"code": "DOCUMENT_MERGE_EMBEDDING_WRITE_FAILED", "message": result["error"]["message"]})

    @staticmethod
    def _filter_requirements_for_docs(docs_cd: str, items: list[Any]) -> list[Any]:
        if docs_cd == "SRS":
            return items
        if docs_cd == "INTERFACE":
            return [item for item in items if not isinstance(item, dict) or _matches_type_or_text(item, {"인터페이스", "ui", "화면", "사용자"})]
        if docs_cd == "TS":
            return [item for item in items if not isinstance(item, dict) or _matches_type_or_text(item, {"기능", "인터페이스", "테스트", "화면"})]
        if docs_cd in {"ERD", "DB"}:
            return [item for item in items if not isinstance(item, dict) or _matches_type_or_text(item, {"기능", "데이터", "db", "테이블", "컬럼", "개인정보"})]
        if docs_cd == "ARCH":
            return [item for item in items if not isinstance(item, dict) or _matches_type_or_text(item, {"기능", "비기능", "보안", "성능", "운영", "연계", "배포", "시스템", "인프라"})]
        return items

    @staticmethod
    def _item_id(item: Any) -> Any:
        if not isinstance(item, dict):
            return None
        return item.get("req_id") or item.get("requirement_id") or item.get("id") or item.get("artifact_id") or item.get("screen_id")

    @staticmethod
    def _success(*, warnings: list[dict[str, Any]], **values: Any) -> dict[str, Any]:
        return {"status": "SUCCESS", **values, "warnings": warnings, "errors": []}

    @staticmethod
    def _failed(code: str, message: str) -> dict[str, Any]:
        return {"status": "FAILED", "failure_type": code, "warnings": [], "errors": [{"code": code, "message": message}]}

    @staticmethod
    def _tool_failed(code: str, result: ToolResult) -> dict[str, Any]:
        return DocumentMergeAgent._failed(code, str(result["error"]["message"]))


def _matches_type_or_text(item: dict[str, Any], keywords: set[str]) -> bool:
    requirement_type = str(item.get("requirement_type") or item.get("type") or "").lower()
    text = " ".join(
        str(item.get(key) or "")
        for key in (
            "requirement_name",
            "req_name",
            "name",
            "description",
            "detail_text",
            "content",
        )
    ).lower()
    return any(keyword.lower() in requirement_type or keyword.lower() in text for keyword in keywords)


def _non_functional_items(items: list[Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in items
        if isinstance(item, dict)
        and not _is_functional_type(item.get("requirement_type") or item.get("type"))
    ]


def _is_functional_type(value: Any) -> bool:
    requirement_type = str(value or "").strip().lower()
    return (
        requirement_type.startswith("기능")
        or requirement_type.startswith("functional")
        or requirement_type == "function"
    )
