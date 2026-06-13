import unittest

from agents.test_scenario.agent import TestScenarioGenerationAgent
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


class TestScenarioAgentTest(unittest.TestCase):
    def test_create_builds_scenarios_cases_steps_and_uses_interface(self) -> None:
        state = _create_state()
        result = TestScenarioGenerationAgent(llm_client=FakeScenarioLLM()).execute(state)
        document = result["integrated_test_scenario_json"]

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(len(document["scenario_json_list"]), 1)
        self.assertEqual(len(document["test_case_json_list"]), 6)
        self.assertEqual(len(document["step_json_list"]), 6)
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

    def test_missing_inputs_fail_and_debug_is_optional(self) -> None:
        missing = TestScenarioGenerationAgent().execute({"docs_cd": "TS", "udt_yn": "N"})
        state = _create_state()
        state["etc"] = {"debug": True}
        debug = TestScenarioGenerationAgent().execute(state)

        self.assertEqual(missing["failure_type"], "TS_REQUIREMENT_MISSING")
        self.assertIn("functional_requirements", debug["debug"])


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
