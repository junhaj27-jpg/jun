import unittest
import tempfile
from pathlib import Path

from agents.test_scenario.agent import TestScenarioGenerationAgent
from agents.test_scenario import prompts as ts_prompts
from agents.validation.agent import ValidationAgent
from tools.result import success_result


class FakeScenarioLLM:
    def chat(self, messages, **kwargs):
        return success_result(
            {
                "scenario": {
                    "scenario_name": "로그인 업무",
                    "source_requirement_ids": ["REQ-001"],
                    "description": "사용자 로그인 기능을 검증한다.",
                }
            }
        )


class FakeFullScenarioLLM:
    def chat(self, messages, **kwargs):
        system_prompt = messages[0]["content"]
        if "요구사항별 업무 시험 시나리오" in system_prompt:
            return success_result(
                {
                    "scenario": {
                        "scenario_name": "로그인 업무",
                        "source_requirement_ids": ["REQ-001"],
                        "description": "로그인 업무를 검증한다.",
                    }
                }
            )
        if "시나리오별 통합시험 케이스" in system_prompt:
            return success_result(
                {
                    "test_case_json_list": [
                        {
                            "case_type": "NORMAL",
                            "test_case_name": "LLM 로그인 정상 케이스",
                            "source_requirement_ids": ["REQ-001"],
                        }
                    ]
                }
            )
        if "시험케이스별 시험 절차" in system_prompt:
            return success_result(
                {
                    "step_json_list": [
                        {
                            "처리내용": "LLM 로그인 화면 진입 후 로그인 버튼을 클릭한다.",
                        }
                    ]
                }
            )
        if "Step별 상세 시험 정보" in system_prompt:
            return success_result(
                {
                    "step_detail_json": {
                        "시험항목": "LLM 로그인 정상 검증",
                        "사전조건": "로그인 화면에 접근한다.",
                        "입력값": "아이디/비밀번호",
                        "예상결과": "로그인 성공",
                        "화면ID": "SCR-LOGIN",
                    }
                }
            )
        return success_result({})


class FakeUpdateScenarioRuleLLM:
    def chat(self, messages, **kwargs):
        system_prompt = messages[0]["content"]
        if "작성 규칙" in system_prompt:
            return success_result(
                {
                    "scenario_rule_applied_json_list": [
                        {
                            "scenario_json_list": [
                                {
                                    "scenario_id": "SCN-LOGIN",
                                    "scenario_name": "로그인 규칙 적용",
                                    "source_requirement_ids": ["REQ-001"],
                                }
                            ],
                            "test_case_json_list": [
                                {
                                    "test_case_id": "TC-LOGIN-001",
                                    "scenario_id": "SCN-LOGIN",
                                    "case_type": "NORMAL",
                                    "test_case_name": "로그인 정상 규칙 적용",
                                }
                            ],
                            "step_json_list": [
                                {
                                    "step_id": "STEP-LOGIN-001",
                                    "test_case_id": "TC-LOGIN-001",
                                    "step_no": 1,
                                    "처리내용": "로그인 버튼 클릭",
                                    "시험항목": "로그인 정상 검증",
                                    "사전조건": "로그인 화면 진입",
                                    "입력값": "아이디/비밀번호",
                                    "예상결과": "로그인 성공",
                                    "화면ID": "SCR-LOGIN",
                                }
                            ],
                        }
                    ]
                }
            )
        if "시나리오 ID" in system_prompt:
            return success_result(
                {
                    "scenario": {
                        "scenario_id": "SCN-LOGIN",
                        "scenario_name": "로그인 규칙 적용",
                        "source_requirement_ids": ["REQ-001"],
                    }
                }
            )
        if "시험 케이스별 품질" in system_prompt:
            return success_result(
                {
                    "test_case": {
                        "test_case_id": "TC-LOGIN-001",
                        "scenario_id": "SCN-LOGIN",
                        "case_type": "NORMAL",
                        "test_case_name": "로그인 정상 규칙 적용",
                    }
                }
            )
        if "Step별 상세 정보를 검토" in system_prompt:
            return success_result(
                {
                    "step": {
                        "step_id": "STEP-LOGIN-001",
                        "test_case_id": "TC-LOGIN-001",
                        "step_no": 1,
                        "처리내용": "로그인 버튼 클릭",
                        "시험항목": "로그인 정상 검증",
                        "사전조건": "로그인 화면 진입",
                        "입력값": "아이디/비밀번호",
                        "예상결과": "로그인 성공",
                        "화면ID": "SCR-LOGIN",
                    }
                }
            )
        return success_result({})


class FakeCompactProcedureLLM:
    def __init__(self):
        self.user_messages = []

    def chat(self, messages, **kwargs):
        system_prompt = messages[0]["content"]
        self.user_messages.append(messages[-1]["content"])
        if "요구사항별 업무 시험 시나리오" in system_prompt:
            return success_result(
                {
                    "scenario": {
                        "scenario_name": "로그인 업무",
                        "source_requirement_ids": ["REQ-001"],
                    }
                }
            )
        if "시나리오별 통합시험 케이스" in system_prompt:
            return success_result(
                {
                    "test_case_json_list": [
                        {
                            "case_type": "NORMAL",
                            "test_case_name": "로그인 정상",
                            "source_requirement_ids": ["REQ-001"],
                            "test_procedure": ["화면 진입", "정보 입력", "로그인 버튼 클릭"],
                            "input_data": ["아이디", "비밀번호"],
                            "test_result": "PASS",
                        }
                    ]
                }
            )
        if "시험케이스별 시험 절차" in system_prompt:
            return success_result({"step_json_list": [{"처리내용": "화면 진입"}]})
        if "Step별 상세 시험 정보" in system_prompt:
            return success_result(
                {
                    "step_detail_json": {
                        "입력값": ["아이디", "비밀번호"],
                        "예상결과": "로그인 성공",
                        "화면ID": "SCR-LOGIN",
                        "test_result": "PASS",
                    }
                }
            )
        return success_result({})


class FakeInvalidCaseLLM(FakeFullScenarioLLM):
    def chat(self, messages, **kwargs):
        if "시나리오별 통합시험 케이스" in messages[0]["content"]:
            return success_result("not a json")
        return super().chat(messages, **kwargs)


class TestScenarioAgentTest(unittest.TestCase):
    def test_create_builds_scenarios_cases_steps_and_uses_interface(self) -> None:
        state = _create_state()
        result = TestScenarioGenerationAgent(llm_client=FakeScenarioLLM()).execute(state)
        document = result["integrated_test_scenario_json"]

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(len(document["scenario_json_list"]), 1)
        self.assertEqual(len(document["test_case_json_list"]), 6)
        self.assertEqual(len(document["step_json_list"]), 6)
        self.assertEqual(len(document["step_detail_json_list"]), 6)
        self.assertEqual(document["step_detail_json_list"][0]["step_id"], document["step_json_list"][0]["step_id"])
        self.assertTrue(
            all(step["화면ID"] == "SCR-LOGIN" for step in document["step_json_list"])
        )
        self.assertIn(
            "로그인 화면 설명",
            document["step_json_list"][0]["예상결과"],
        )
        self.assertIs(state["agent_outputs"]["test_scenario_generation_agent"], result)
        self.assertNotIn("integrated_test_scenario_json", state)
        self.assertNotIn("debug", result)

    def test_create_uses_parallel_llm_case_and_step_detail_stages(self) -> None:
        state = _create_state()
        result = TestScenarioGenerationAgent(llm_client=FakeFullScenarioLLM()).execute(state)
        document = result["integrated_test_scenario_json"]

        self.assertEqual(document["test_case_json_list"][0]["test_case_name"], "LLM 로그인 정상 케이스")
        self.assertEqual(document["step_json_list"][0]["처리내용"], "LLM 로그인 화면 진입 후 로그인 버튼을 클릭한다.")
        self.assertEqual(document["step_json_list"][0]["시험항목"], "LLM 로그인 정상 검증")
        self.assertEqual(document["step_json_list"][0]["입력값"], "아이디/비밀번호")
        self.assertEqual(document["step_json_list"][0]["화면ID"], "SCR-LOGIN")

    def test_created_output_passes_current_ts_validator(self) -> None:
        state = _create_state()
        TestScenarioGenerationAgent().execute(state)
        validation = ValidationAgent().execute(state)

        self.assertEqual(validation["validation_result"]["validation_status"], "PASS")

    def test_update_refines_existing_artifact_rules(self) -> None:
        state = {
            "docs_cd": "TS",
            "udt_yn": "Y",
            "agent_outputs": {
                "document_merge_agent": {
                    "integrated_artifact_json_list": [
                        {
                            "scenario_json_list": [{"scenario_name": "로그인"}],
                            "test_case_json_list": [{"name": "로그인 정상 처리"}],
                            "step_json_list": [{"action": "로그인 버튼 클릭"}],
                        }
                    ]
                }
            },
        }
        result = TestScenarioGenerationAgent().execute(state)
        document = result["integrated_test_scenario_json"]

        self.assertEqual(document["scenario_json_list"][0]["scenario_id"], "SCN-001")
        self.assertEqual(document["test_case_json_list"][0]["case_type"], "NORMAL")
        step = document["step_json_list"][0]
        self.assertEqual(step["처리내용"], "로그인 버튼 클릭")
        self.assertEqual(step["화면ID"], "N/A")
        self.assertTrue(step["입력값"])
        self.assertTrue(step["예상결과"])
        self.assertEqual(
            document["step_detail_json_list"][0]["step_id"],
            document["step_json_list"][0]["step_id"],
        )

    def test_update_applies_scenario_rules_before_refinement(self) -> None:
        state = {
            "docs_cd": "TS",
            "udt_yn": "Y",
            "etc": {"debug": True},
            "agent_outputs": {
                "document_merge_agent": {
                    "integrated_artifact_json_list": [
                        {
                            "scenario_json_list": [{"scenario_name": "로그인"}],
                            "test_case_json_list": [{"name": "로그인 정상 처리"}],
                            "step_json_list": [{"action": "로그인 버튼 클릭"}],
                        }
                    ]
                }
            },
        }
        result = TestScenarioGenerationAgent(llm_client=FakeUpdateScenarioRuleLLM()).execute(state)
        document = result["integrated_test_scenario_json"]

        self.assertEqual(document["scenario_json_list"][0]["scenario_name"], "로그인 규칙 적용")
        self.assertEqual(document["test_case_json_list"][0]["test_case_id"], "TC-LOGIN-001")
        self.assertEqual(document["step_detail_json_list"][0]["화면ID"], "SCR-LOGIN")
        self.assertIn("scenario_rule_applied_json_list", result["debug"])

    def test_missing_inputs_fail_and_debug_is_optional(self) -> None:
        missing = TestScenarioGenerationAgent().execute({"docs_cd": "TS", "udt_yn": "N"})
        state = _create_state()
        state["etc"] = {"debug": True}
        debug = TestScenarioGenerationAgent().execute(state)

        self.assertEqual(missing["failure_type"], "TS_REQUIREMENT_MISSING")
        self.assertIn("functional_requirements", debug["debug"])

    def test_create_compacts_requirements_sanitizes_cases_and_fills_missing_procedure_steps(self) -> None:
        llm = FakeCompactProcedureLLM()
        state = _create_state()
        state["etc"] = {"debug": True}
        state["agent_outputs"]["document_merge_agent"]["integrated_requirement_json_list"][0]["raw_text"] = "삭제되어야 하는 원문" * 200

        result = TestScenarioGenerationAgent(llm_client=llm).execute(state)
        document = result["integrated_test_scenario_json"]
        first_case = document["test_case_json_list"][0]
        first_case_steps = [
            step for step in document["step_json_list"]
            if step["test_case_id"] == first_case["test_case_id"]
        ]

        self.assertNotIn("raw_text", llm.user_messages[0])
        self.assertIn("compacted_functional_requirements", result["debug"])
        self.assertIsNone(first_case["test_result"])
        self.assertEqual(first_case["input_data"], "아이디 비밀번호")
        self.assertEqual([step["처리내용"] for step in first_case_steps], ["화면 진입", "정보 입력", "로그인 버튼 클릭"])
        self.assertTrue(all(step["test_result"] is None for step in document["step_json_list"]))
        self.assertEqual(document["step_json_list"][0]["입력값"], "아이디 비밀번호")

    def test_invalid_llm_output_is_saved_to_raw_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            original_dir = ts_prompts.TS_RAW_OUTPUT_DIR
            ts_prompts.TS_RAW_OUTPUT_DIR = root
            try:
                result = TestScenarioGenerationAgent(llm_client=FakeInvalidCaseLLM()).execute(_create_state())
            finally:
                ts_prompts.TS_RAW_OUTPUT_DIR = original_dir

            raw_paths = [
                warning.get("raw_output_path")
                for warning in result["warnings"]
                if warning.get("raw_output_path")
            ]
            self.assertTrue(raw_paths)
            self.assertTrue(Path(raw_paths[0]).exists())
            self.assertIn("not a json", Path(raw_paths[0]).read_text(encoding="utf-8"))


def _create_state():
    return {
        "docs_cd": "TS",
        "udt_yn": "N",
        "agent_outputs": {
            "document_merge_agent": {
                "integrated_requirement_json_list": [
                    {
                        "req_id": "REQ-001",
                        "req_name": "로그인",
                        "requirement_type": "기능",
                        "detail_text": "사용자는 로그인할 수 있어야 한다.",
                    },
                    {
                        "req_id": "NFR-001",
                        "req_name": "응답시간",
                        "requirement_type": "성능",
                    },
                ],
                "reference_interface_json_list": [
                    {
                        "screen_id": "SCR-LOGIN",
                        "matched_requirement_ids": ["REQ-001"],
                        "description": "로그인 화면 설명",
                    }
                ],
            }
        },
    }


if __name__ == "__main__":
    unittest.main()
