# 통합시험 시나리오의 구조와 내용을 검증합니다.

from typing import Any

from agents.validation.schemas import duplicate_values, first_list, is_empty, make_check
from workflow.state import WorkflowState


TARGET = "test_scenario_generation_agent"


def validate(state: WorkflowState) -> list[dict[str, Any]]:
    document = state.get("agent_outputs", {}).get(TARGET, {}).get(
        "integrated_test_scenario_json"
    )
    checks = [
        make_check("TS_OUTPUT_001", "시험 시나리오 출력 존재 검증", isinstance(document, dict) and bool(document), failure_type="TS_OUTPUT_MISSING", message="integrated_test_scenario_json이 없거나 비어 있습니다.", target_agent=TARGET)
    ]
    if not isinstance(document, dict) or not document:
        return checks

    scenarios = first_list(document, "scenario_json_list", "scenarios")
    cases = first_list(document, "test_case_json_list", "test_cases")
    steps = first_list(document, "step_json_list", "steps")
    checks.append(
        make_check("TS_SCHEMA_001", "시험 시나리오 필수 구조 검증", bool(scenarios) and bool(cases) and bool(steps), failure_type="TS_SCHEMA_ERROR", message="scenario_json_list, test_case_json_list, step_json_list가 필요합니다.", target_agent=TARGET)
    )
    checks.extend(
        [
            make_check("TS_SCENARIO_001", "시나리오 ID 중복 검증", not (scenario_duplicates := duplicate_values(scenarios, "scenario_id", "id")), failure_type="TS_SCENARIO_ID_DUPLICATED", message="중복된 시나리오 ID가 있습니다.", target_agent=TARGET, target_scope=scenario_duplicates),
            make_check("TS_CASE_001", "시험케이스 ID 중복 검증", not (case_duplicates := duplicate_values(cases, "test_case_id", "case_id", "id")), failure_type="TS_TEST_CASE_ID_DUPLICATED", message="중복된 시험케이스 ID가 있습니다.", target_agent=TARGET, target_scope=case_duplicates),
        ]
    )
    missing_detail, duplicate_steps = [], []
    step_keys: set[tuple[str, str]] = set()
    required_aliases = [
        ("처리내용", "process", "action"),
        ("시험항목", "test_item"),
        ("사전조건", "precondition"),
        ("입력값", "input", "input_value"),
        ("예상결과", "expected_result"),
        ("화면ID", "screen_id"),
    ]
    for index, step in enumerate(steps):
        scope = str(step.get("step_id") or step.get("step_no") or index) if isinstance(step, dict) else str(index)
        if isinstance(step, dict):
            key = (str(step.get("test_case_id") or ""), str(step.get("step_no") or ""))
            if key in step_keys:
                duplicate_steps.append(scope)
            step_keys.add(key)
        if not isinstance(step, dict) or any(
            all(is_empty(step.get(alias)) for alias in aliases) for aliases in required_aliases
        ):
            missing_detail.append(scope)
    requirement_ids = _ids_from_requirements(state)
    scenario_requirement_ids = {
        str(req_id)
        for scenario in scenarios if isinstance(scenario, dict)
        for req_id in scenario.get("source_requirement_ids", [])
    }
    missing_requirements = sorted(requirement_ids - scenario_requirement_ids)
    interface_ids = _interface_ids(state)
    invalid_interface_steps = [
        str(step.get("step_id") or index)
        for index, step in enumerate(steps) if isinstance(step, dict)
        and interface_ids and str(step.get("screen_id") or step.get("화면ID")) not in interface_ids
    ]
    case_types = {str(case.get("case_type") or "").upper() for case in cases if isinstance(case, dict)}
    scenario_case_map: dict[str, set[str]] = {}
    for case in cases:
        if isinstance(case, dict):
            scenario_case_map.setdefault(str(case.get("scenario_id") or ""), set()).add(str(case.get("case_type") or "").upper())
    trace_missing = [
        str(case.get("test_case_id") or index)
        for index, case in enumerate(cases) if isinstance(case, dict)
        and is_empty(case.get("scenario_id"))
    ]
    missing_quality_cases = [
        scenario_id
        for scenario_id, types in scenario_case_map.items()
        if scenario_id and not {"AUTHORIZATION", "STATE_CHANGE", "DATA_INTEGRITY"}.intersection(types)
    ]
    checks.extend(
        [
        make_check("TS_STEP_001", "Step 상세 정보 누락 검증", not missing_detail, failure_type="TS_STEP_DETAIL_MISSING", message="일부 Step에 필수 상세 정보가 누락되었습니다.", target_agent=TARGET, target_scope=missing_detail),
        make_check("TS_STEP_002", "Step 번호 중복 검증", not duplicate_steps, failure_type="TS_STEP_MISSING", message="시험케이스 내 Step 번호가 중복되었습니다.", target_agent=TARGET, target_scope=duplicate_steps),
        make_check("TS_COVERAGE_001", "요구사항 커버리지 검증", not missing_requirements, failure_type="TS_REQUIREMENT_COVERAGE_MISSING", message="시나리오에 반영되지 않은 기능 요구사항이 있습니다.", target_agent=TARGET, target_scope=missing_requirements),
        make_check("TS_INTERFACE_001", "인터페이스 화면 매핑 검증", not invalid_interface_steps, failure_type="TS_INTERFACE_MAPPING_MISSING", message="참조 인터페이스와 매핑되지 않은 Step이 있습니다.", target_agent=TARGET, target_scope=invalid_interface_steps),
        make_check("TS_CASE_002", "정상 케이스 존재 검증", "NORMAL" in case_types, failure_type="TS_NORMAL_CASE_MISSING", message="정상 시험 케이스가 없습니다.", target_agent=TARGET),
        make_check("TS_CASE_003", "예외 케이스 존재 검증", "EXCEPTION" in case_types, failure_type="TS_EXCEPTION_CASE_MISSING", message="예외 시험 케이스가 없습니다.", target_agent=TARGET),
        make_check("TS_CASE_004", "권한/상태/데이터 검증 케이스 존재 검증", not missing_quality_cases, failure_type="TS_TRACEABILITY_MISSING", message="권한/상태변경/데이터정합성 검증 케이스가 부족합니다.", target_agent=TARGET, target_scope=missing_quality_cases, severity="MEDIUM", warning=True),
        make_check("TS_TRACE_001", "Scenario-Test Case 추적성 검증", not trace_missing, failure_type="TS_TRACEABILITY_MISSING", message="scenario_id가 없는 시험 케이스가 있습니다.", target_agent=TARGET, target_scope=trace_missing),
        _meeting_check(state),
        ]
    )
    return checks


def _ids_from_requirements(state: WorkflowState) -> set[str]:
    items = state.get("agent_outputs", {}).get("document_merge_agent", {}).get("integrated_requirement_json_list") or []
    return {
        str(item.get("req_id") or item.get("requirement_id"))
        for item in items if isinstance(item, dict)
        and str(item.get("requirement_type") or "").lower() in {"기능", "functional", "function"}
    }


def _interface_ids(state: WorkflowState) -> set[str]:
    items = state.get("agent_outputs", {}).get("document_merge_agent", {}).get("reference_interface_json_list") or []
    return {str(item.get("screen_id") or item.get("interface_id")) for item in items if isinstance(item, dict)}


def _meeting_check(state: WorkflowState) -> dict[str, Any]:
    artifact = state.get("agent_outputs", {}).get("document_merge_agent", {}).get("integrated_artifact_json_list")
    return make_check("TS_MEETING_001", "수정 회의록 반영 검증", state.get("udt_yn") != "Y" or bool(artifact), failure_type="TS_MEETING_CHANGE_MISSING", message="회의록이 반영된 통합 TS 산출물을 확인할 수 없습니다.", target_agent="document_merge_agent")
