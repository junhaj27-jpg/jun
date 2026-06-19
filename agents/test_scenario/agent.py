# 통합시험 시나리오 생성 및 수정 Agent의 실행 진입점입니다.

from typing import Any

from agents.test_scenario.prompts import compact_requirement_for_ts
from agents.test_scenario.processors import (
    apply_scenario_rules,
    build_step_detail_list,
    filter_function_requirements,
    generate_scenarios,
    generate_steps,
    generate_steps_with_llm,
    generate_test_cases,
    refine_scenarios,
    refine_steps,
    refine_test_cases,
)
from tools.llm.llm_client import LLMClient
from workflow.state import WorkflowState


class TestScenarioGenerationAgent:
    def __init__(self, *, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client

    def execute(self, state: WorkflowState) -> dict[str, Any]:
        if str(state.get("docs_cd", "")).upper() != "TS":
            return self._store(state, self._failed("TEST_SCENARIO_INVALID_DOCS_CD", "test_scenario_generation_agent는 TS 산출물에서만 실행할 수 있습니다."))

        mode = str(state.get("udt_yn", "")).upper()
        document_merge = state.get("agent_outputs", {}).get("document_merge_agent", {})
        if mode == "N":
            output = self._create(document_merge, state)
        elif mode == "Y":
            output = self._update(document_merge, state)
        else:
            output = self._failed("TEST_SCENARIO_INVALID_MODE", f"허용되지 않은 udt_yn입니다: {mode}")
        return self._store(state, output)

    def _create(self, document_merge: dict[str, Any], state: WorkflowState) -> dict[str, Any]:
        requirements = document_merge.get("integrated_requirement_json_list")
        interfaces = document_merge.get("reference_interface_json_list")
        if not isinstance(requirements, list) or not requirements:
            return self._failed("TS_REQUIREMENT_MISSING", "integrated_requirement_json_list가 필요합니다.")
        if not isinstance(interfaces, list) or not interfaces:
            return self._failed("TS_INTERFACE_REFERENCE_MISSING", "reference_interface_json_list가 필요합니다.")
        functional = filter_function_requirements(requirements)
        if not functional:
            return self._failed("TS_FUNCTION_REQUIREMENT_MISSING", "기능 요구사항이 없습니다.")

        compacted_functional = [compact_requirement_for_ts(item) for item in functional]
        scenarios, warnings = generate_scenarios(compacted_functional, llm_client=self.llm_client)
        cases, case_warnings = generate_test_cases(scenarios, llm_client=self.llm_client)
        steps, step_warnings = generate_steps_with_llm(cases, interfaces, llm_client=self.llm_client)
        warnings.extend(case_warnings)
        warnings.extend(step_warnings)
        return self._success(
            state,
            scenarios,
            cases,
            steps,
            warnings,
            {
                "functional_requirements": functional,
                "compacted_functional_requirements": compacted_functional,
            },
        )

    def _update(self, document_merge: dict[str, Any], state: WorkflowState) -> dict[str, Any]:
        artifacts = document_merge.get("integrated_artifact_json_list")
        if not isinstance(artifacts, list) or not artifacts:
            return self._failed("TS_ARTIFACT_MISSING", "integrated_artifact_json_list가 필요합니다.")

        rule_applied_artifacts, warnings = apply_scenario_rules(
            [item for item in artifacts if isinstance(item, dict)],
            llm_client=self.llm_client,
        )
        scenarios = _collect_list(rule_applied_artifacts, "scenario_json_list", "scenarios")
        cases = _collect_list(rule_applied_artifacts, "test_case_json_list", "test_cases")
        steps = _collect_list(rule_applied_artifacts, "step_json_list", "steps")
        if not scenarios:
            scenarios = [item for item in rule_applied_artifacts if isinstance(item, dict)]
        scenarios, scenario_warnings = refine_scenarios(scenarios, llm_client=self.llm_client)
        if cases:
            cases, case_warnings = refine_test_cases(cases, llm_client=self.llm_client)
        else:
            cases, case_warnings = generate_test_cases(scenarios, llm_client=self.llm_client)
        if steps:
            steps, step_warnings = refine_steps(steps, llm_client=self.llm_client)
        else:
            steps, step_warnings = generate_steps(cases, [])
        warnings.extend(scenario_warnings)
        warnings.extend(case_warnings)
        warnings.extend(step_warnings)
        return self._success(
            state,
            scenarios,
            cases,
            steps,
            warnings,
            {
                "source_artifacts": artifacts,
                "scenario_rule_applied_json_list": rule_applied_artifacts,
            },
        )

    @staticmethod
    def _success(
        state: WorkflowState,
        scenarios: list[dict[str, Any]],
        cases: list[dict[str, Any]],
        steps: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
        debug: dict[str, Any],
    ) -> dict[str, Any]:
        output: dict[str, Any] = {
            "status": "SUCCESS",
            "integrated_test_scenario_json": {
                "scenario_json_list": scenarios,
                "test_case_json_list": cases,
                "step_json_list": steps,
                "step_detail_json_list": build_step_detail_list(steps),
            },
            "warnings": warnings,
            "errors": [],
        }
        if bool(state.get("etc", {}).get("debug")):
            output["debug"] = debug
        return output

    @staticmethod
    def _store(state: WorkflowState, output: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("agent_outputs", {})["test_scenario_generation_agent"] = output
        return output

    @staticmethod
    def _failed(code: str, message: str) -> dict[str, Any]:
        return {
            "status": "FAILED",
            "failure_type": code,
            "warnings": [],
            "errors": [{"code": code, "message": message}],
        }


def _collect_list(artifacts: list[Any], *keys: str) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        for key in keys:
            value = artifact.get(key)
            if isinstance(value, list):
                collected.extend(item for item in value if isinstance(item, dict))
    return collected
