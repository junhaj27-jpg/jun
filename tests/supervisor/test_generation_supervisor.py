import unittest
from typing import Any

from supervisor.evaluate.result_checker import check_agent_result
from supervisor.generation_supervisor import run_generation_supervisor
from supervisor.plan.execution_harness import EXECUTION_HARNESS
from supervisor.plan.plan_builder import build_plan
from supervisor.registry.agent_registry import AgentRegistry, default_agent_registry
from supervisor.replan.replan_builder import build_replan


AGENT_NAMES = {
    agent_name
    for agent_names in EXECUTION_HARNESS.values()
    for agent_name in agent_names
}


def success_output(**outputs: Any) -> dict[str, Any]:
    return {"status": "SUCCESS", **outputs, "warnings": [], "errors": []}


def successful_registry() -> AgentRegistry:
    return AgentRegistry(
        {
            "document_merge_agent": lambda state: success_output(
                integrated_requirement_json_list=[{"stub": True}],
                integrated_artifact_json_list=[{"stub": True}],
                existing_output_raw_json={"stub": True},
                meeting_change_items=[{"stub": True}],
                reference_erd_json_list=[{"stub": True}],
                reference_interface_json_list=[{"stub": True}],
            ),
            "requirement_generation_agent": lambda state: success_output(
                final_requirement_json_list=[{"stub": True}]
            ),
            "image_analysis_agent": lambda state: success_output(
                interface_image_analysis_json_list=[{"stub": True}]
            ),
            "test_scenario_generation_agent": lambda state: success_output(
                integrated_test_scenario_json={"stub": True}
            ),
            "architecture_analysis_agent": lambda state: success_output(
                architecture_structure_json={"stub": True},
                architecture_document_json={"stub": True},
            ),
            "data_structure_design_agent": lambda state: success_output(
                erd_entity_json={"stub": True},
                erd_mermaid_json={"stub": True},
                db_design_json={"stub": True},
            ),
            "mermaid_generation_agent": lambda state: success_output(
                mermaid_code="stub",
                mermaid_image_path="/tmp/stub.png",
            ),
            "validation_agent": lambda state: success_output(
                validation_result={"validation_status": "PASS", "checks": []}
            ),
        }
    )


def registry_with_validation(validation_agent) -> AgentRegistry:
    registry = successful_registry()
    registry.register("validation_agent", validation_agent)
    return registry


class GenerationSupervisorTest(unittest.TestCase):
    def test_all_initial_plans_follow_required_order(self) -> None:
        for docs_cd, udt_yn in EXECUTION_HARNESS:
            plan = build_plan(docs_cd, udt_yn)
            agents = [step["agent"] for step in plan["steps"]]

            self.assertEqual(agents[0], "document_merge_agent")
            self.assertEqual(agents[-1], "validation_agent")

    def test_required_output_missing_is_failure(self) -> None:
        result = check_agent_result(
            "requirement_generation_agent",
            {"status": "SUCCESS", "final_requirement_json_list": [], "errors": []},
            ["final_requirement_json_list"],
        )

        self.assertFalse(result["success"])

    def test_successful_mock_agents_reduce_to_empty_document(self) -> None:
        state = {
            "project_sn": 1,
            "docs_cd": "ERD",
            "udt_yn": "N",
            "max_round": 3,
        }

        result = run_generation_supervisor(state, successful_registry())

        self.assertEqual(result["next_action"], "EXPORT")
        self.assertEqual(
            result["final_document_json"],
            {"docs_cd": "ERD", "erd_entity_json": {}, "mermaid_image_path": ""},
        )
        self.assertIn("document_merge_agent", result["agent_outputs"])
        self.assertIn("validation_agent", result["agent_outputs"])

    def test_default_empty_stubs_fail_evaluation(self) -> None:
        result = run_generation_supervisor(
            {"project_sn": 1, "docs_cd": "SRS", "udt_yn": "N", "max_round": 1}
        )

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["next_action"], "END")

    def test_validation_fail_replans_then_reduces(self) -> None:
        calls = {"count": 0}

        def validation_agent(state) -> dict[str, Any]:
            calls["count"] += 1
            if calls["count"] == 1:
                return {
                    "status": "SUCCESS",
                    "validation_result": {
                        "validation_status": "FAIL",
                        "checks": [
                            {
                                "status": "FAIL",
                                "failure_type": "ERD_MERMAID_RENDER_FAILED",
                            }
                        ],
                    },
                    "warnings": [],
                    "errors": [],
                }
            return {
                "status": "SUCCESS",
                "validation_result": {"validation_status": "PASS", "checks": []},
                "warnings": [],
                "errors": [],
            }

        result = run_generation_supervisor(
            {
                "project_sn": 1,
                "docs_cd": "ERD",
                "udt_yn": "N",
                "max_round": 3,
            },
            registry_with_validation(validation_agent),
        )

        self.assertEqual(result["current_round"], 2)
        self.assertEqual(result["execution_plan"]["replan_reason"], "ERD_MERMAID_RENDER_FAILED")
        agents = [step["agent"] for step in result["execution_plan"]["steps"]]
        self.assertEqual(
            agents,
            ["document_merge_agent", "mermaid_generation_agent", "validation_agent"],
        )
        self.assertEqual(result["next_action"], "EXPORT")

    def test_max_round_failure_ends_supervisor(self) -> None:
        def validation_agent(state) -> dict[str, Any]:
            return {
                "status": "SUCCESS",
                "validation_result": {
                    "validation_status": "FAIL",
                    "checks": [
                        {"status": "FAIL", "failure_type": "DB_COLUMN_MISSING"}
                    ],
                },
                "warnings": [],
                "errors": [],
            }

        result = run_generation_supervisor(
            {
                "project_sn": 1,
                "docs_cd": "DB",
                "udt_yn": "N",
                "max_round": 2,
            },
            registry_with_validation(validation_agent),
        )

        self.assertEqual(result["current_round"], 2)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["next_action"], "END")

    def test_replan_keeps_mandatory_agents(self) -> None:
        plan = build_replan(
            "ARCH",
            "N",
            "ARCH_COMPONENT_MISSING",
            current_round=1,
            max_round=3,
        )
        agents = [step["agent"] for step in plan["steps"]]

        self.assertEqual(agents[0], "document_merge_agent")
        self.assertEqual(agents[-1], "validation_agent")


if __name__ == "__main__":
    unittest.main()
