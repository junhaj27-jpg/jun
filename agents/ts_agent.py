import json
import os
import re
import time
from collections import Counter
from typing import Any

from agents.ts_prompt import build_prompt
from services.llm_client import call_llm_messages

TS_FIELD_MAX_CHARS = int(os.getenv("TS_FIELD_MAX_CHARS", "2500"))
TS_LIST_ITEM_MAX_CHARS = int(os.getenv("TS_LIST_ITEM_MAX_CHARS", "800"))
TS_REQUIREMENT_MAX_CHARS = int(os.getenv("TS_REQUIREMENT_MAX_CHARS", "8000"))
TS_MAX_TOKENS = int(os.getenv("TS_MAX_TOKENS", "4096"))


def _strip_markdown_json(raw_output: str) -> str:
    text = raw_output.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:])
    if text.endswith("```"):
        text = text[:-3].strip()

    if not text.startswith("{"):
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            text = match.group(0)
    return text


def _truncate_text(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n...(입력 길이 제한으로 일부 생략)"


def _compact_value(value: Any, max_chars: int = TS_FIELD_MAX_CHARS) -> Any:
    if isinstance(value, str):
        return _truncate_text(value, max_chars)
    if isinstance(value, list):
        compacted = []
        total_chars = 0
        for item in value:
            compacted_item = _compact_value(item, TS_LIST_ITEM_MAX_CHARS)
            item_size = len(json.dumps(compacted_item, ensure_ascii=False))
            if total_chars + item_size > max_chars:
                compacted.append("...(입력 길이 제한으로 나머지 항목 생략)")
                break
            compacted.append(compacted_item)
            total_chars += item_size
        return compacted
    if isinstance(value, dict):
        return {
            key: _compact_value(item, max_chars)
            for key, item in value.items()
            if key not in {"raw_text", "page_text", "full_text", "chunks", "tables"}
        }
    return value


def compact_requirement_for_ts(requirement: dict[str, Any]) -> dict[str, Any]:
    preferred_keys = [
        "requirement_id",
        "requirement_name",
        "requirement_type",
        "description",
        "constraints",
        "validation_criteria",
        "priority",
        "source",
    ]
    compacted = {
        key: _compact_value(requirement.get(key))
        for key in preferred_keys
        if key in requirement
    }
    payload = json.dumps(compacted, ensure_ascii=False)
    if len(payload) <= TS_REQUIREMENT_MAX_CHARS:
        return compacted

    for key in ["source", "constraints", "validation_criteria", "description"]:
        if key in compacted:
            compacted[key] = _compact_value(compacted[key], max(TS_FIELD_MAX_CHARS // 2, 1000))
        payload = json.dumps(compacted, ensure_ascii=False)
        if len(payload) <= TS_REQUIREMENT_MAX_CHARS:
            break
    return compacted


def parse_and_validate(raw_output: str) -> tuple[dict[str, Any] | None, str]:
    try:
        data = json.loads(_strip_markdown_json(raw_output))
    except json.JSONDecodeError as exc:
        return None, f"JSON 파싱 실패: {exc}"

    if "scenarios" not in data:
        return None, "필수 키 누락: 'scenarios'"
    if "cases" not in data:
        return None, "필수 키 누락: 'cases'"

    for i, scenario in enumerate(data["scenarios"]):
        for key in ["scenario_id", "scenario_name", "scenario_description", "test_cases"]:
            if key not in scenario:
                return None, f"scenarios[{i}] 필수 키 누락: '{key}'"
        for j, test_case in enumerate(scenario["test_cases"]):
            for key in ["test_case_id", "test_case_description", "test_procedure", "scenario_detail"]:
                if key not in test_case:
                    return None, f"scenarios[{i}].test_cases[{j}] 필수 키 누락: '{key}'"

    required_case_keys = [
        "round",
        "scenario_id",
        "scenario_name",
        "test_case_id",
        "sequence",
        "process_content",
        "test_item",
        "input_data",
        "expected_result",
        "screen_id",
    ]
    for i, case in enumerate(data["cases"]):
        for key in required_case_keys:
            if key not in case:
                return None, f"cases[{i}] 필수 키 누락: '{key}'"
        if case.get("test_result") is not None:
            return None, f"cases[{i}].test_result는 설계 단계에서 null이어야 합니다."
        if not isinstance(case.get("input_data"), str):
            return None, f"cases[{i}].input_data는 문자열이어야 합니다."

    return data, ""


def fill_missing_cases(data: dict[str, Any]) -> dict[str, Any]:
    for scenario in data["scenarios"]:
        scenario_id = scenario["scenario_id"]
        scenario_name = scenario["scenario_name"]

        for test_case in scenario["test_cases"]:
            test_case_id = test_case["test_case_id"]
            procedures = test_case.get("test_procedure", [])
            existing = {
                case["sequence"]: case
                for case in data["cases"]
                if case["test_case_id"] == test_case_id
            }

            if len(existing) >= len(procedures):
                continue

            template = existing[max(existing.keys())] if existing else {}
            for sequence in range(1, len(procedures) + 1):
                if sequence in existing:
                    continue
                data["cases"].append(
                    {
                        "round": template.get("round", 1),
                        "scenario_id": scenario_id,
                        "scenario_name": scenario_name,
                        "test_case_id": test_case_id,
                        "sequence": sequence,
                        "process_content": procedures[sequence - 1],
                        "test_item": "(자동 보완 필요)",
                        "precondition": None,
                        "input_data": "(자동 보완 필요)",
                        "expected_result": "(자동 보완 필요)",
                        "screen_id": template.get("screen_id", ""),
                        "test_result": None,
                        "note": "자동 보완된 행입니다. 내용을 검토하고 수정하세요.",
                    }
                )

    data["cases"].sort(key=lambda case: (case["scenario_id"], case["test_case_id"], case["sequence"]))
    return data


def generate_test_scenarios(
    requirement_doc: dict[str, Any],
    ui_screens_raw: list[str] | None = None,
    *,
    max_retries: int = 1,
) -> dict[str, Any]:
    requirements = requirement_doc.get("requirements", [])
    all_scenarios: list[dict[str, Any]] = []
    all_cases: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for index, requirement in enumerate(requirements, start=1):
        requirement_id = requirement.get("requirement_id", f"REQ-{index}")
        compacted_requirement = compact_requirement_for_ts(requirement)
        single_req_json = json.dumps({"requirements": [compacted_requirement]}, ensure_ascii=False, indent=2)
        messages = build_prompt(single_req_json, ui_screens_raw)

        parsed = None
        last_error = ""
        started_at = time.time()
        for _ in range(max_retries + 1):
            try:
                raw_output = call_llm_messages(
                    messages,
                    temperature=0.2,
                    max_tokens=TS_MAX_TOKENS,
                    timeout=600,
                )
            except Exception as exc:
                last_error = f"LLM 호출 실패: {exc}"
                break

            parsed, last_error = parse_and_validate(raw_output)
            if not last_error and parsed:
                break
            messages.append({"role": "assistant", "content": raw_output})
            messages.append(
                {
                    "role": "user",
                    "content": f"위 응답은 오류가 있습니다: {last_error}. 스키마에 맞는 JSON만 다시 출력하세요.",
                }
            )

        if not parsed:
            errors.append({"requirement_id": requirement_id, "error": last_error})
            continue

        parsed = fill_missing_cases(parsed)
        all_scenarios.extend(parsed.get("scenarios", []))
        all_cases.extend(parsed.get("cases", []))
        print(f"[PASS] {requirement_id} 통합 시험 시나리오 생성 완료 ({time.time() - started_at:.1f}초)")

    return {
        "scenarios": all_scenarios,
        "cases": all_cases,
        "errors": errors,
        "summary": summarize_test_scenarios({"scenarios": all_scenarios, "cases": all_cases}),
    }


def summarize_test_scenarios(data: dict[str, Any]) -> dict[str, Any]:
    counter = Counter(case["test_case_id"] for case in data.get("cases", []))
    return {
        "scenario_count": len(data.get("scenarios", [])),
        "case_row_count": len(data.get("cases", [])),
        "case_rows_by_test_case": dict(counter),
    }
