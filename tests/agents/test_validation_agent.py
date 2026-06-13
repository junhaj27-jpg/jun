import copy
import unittest

from agents.validation.agent import ValidationAgent


class ValidationAgentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = ValidationAgent()

    def test_srs_pass_and_partial_pass(self) -> None:
        functional = {
            "req_id": "SFR-001",
            "req_name": "로그인",
            "requirement_type": "기능",
            "detail_text": "사용자가 로그인한다.",
            "source_req_ids": ["RFP-001"],
            "validation_criteria": ["로그인 성공 여부를 확인한다."],
        }
        non_functional = {
            **functional,
            "req_id": "NFR-001",
            "req_name": "응답시간",
            "requirement_type": "성능",
        }
        passed = self.agent.execute(
            {
                "docs_cd": "SRS",
                "agent_outputs": {
                    "requirement_generation_agent": {
                        "final_requirement_json_list": [functional, non_functional]
                    }
                },
            }
        )
        partial = self.agent.execute(
            {
                "docs_cd": "SRS",
                "agent_outputs": {
                    "requirement_generation_agent": {
                        "final_requirement_json_list": [functional]
                    }
                },
            }
        )

        self.assertEqual(passed["validation_result"]["validation_status"], "PASS")
        self.assertEqual(partial["validation_result"]["validation_status"], "PARTIAL_PASS")
        self.assertEqual(partial["validation_result"]["warning_count"], 1)

    def test_interface_failure_returns_target_agent_and_scope(self) -> None:
        result = self.agent.execute(
            {
                "docs_cd": "INTERFACE",
                "agent_outputs": {
                    "image_analysis_agent": {
                        "interface_image_analysis_json_list": [
                            {
                                "screen_id": "SCR-001",
                                "screen_name": "로그인",
                                "description": "로그인 화면",
                                "matched_requirement_ids": ["SFR-001"],
                                "match_status": "MATCHED",
                            }
                        ]
                    }
                },
            }
        )
        check = _failure(result, "INTERFACE_IMAGE_MAPPING_MISSING")
        self.assertEqual(check["target_agent"], "image_analysis_agent")
        self.assertEqual(check["target_scope"], ["SCR-001"])

    def test_ts_detects_missing_step_detail(self) -> None:
        result = self.agent.execute(
            {
                "docs_cd": "TS",
                "agent_outputs": {
                    "test_scenario_generation_agent": {
                        "integrated_test_scenario_json": {
                            "scenario_json_list": [{"scenario_id": "SC-1"}],
                            "test_case_json_list": [{"test_case_id": "TC-1"}],
                            "step_json_list": [{"step_id": "STEP-1", "처리내용": "실행"}],
                        }
                    }
                },
            }
        )
        self.assertEqual(
            _failure(result, "TS_STEP_DETAIL_MISSING")["target_scope"],
            ["STEP-1"],
        )

    def test_erd_detects_pk_and_mermaid_failures(self) -> None:
        result = self.agent.execute(
            {
                "docs_cd": "ERD",
                "agent_outputs": {
                    "data_structure_design_agent": {
                        "erd_entity_json": {
                            "tables": [
                                {
                                    "table_id": "T1",
                                    "logical_name": "사용자",
                                    "physical_name": "users",
                                    "columns": [
                                        {
                                            "column_id": "C1",
                                            "logical_name": "이름",
                                            "physical_name": "name",
                                            "data_type": "varchar",
                                            "nullable": False,
                                            "constraints": [],
                                        }
                                    ],
                                }
                            ]
                        },
                        "erd_mermaid_json": {"tables": []},
                    },
                    "mermaid_generation_agent": {
                        "mermaid_code": "",
                        "mermaid_image_path": "",
                    },
                },
            }
        )
        self.assertEqual(_failure(result, "ERD_PK_MISSING")["target_agent"], "data_structure_design_agent")
        self.assertEqual(_failure(result, "ERD_MERMAID_RENDER_FAILED")["target_agent"], "mermaid_generation_agent")

    def test_db_and_arch_route_to_document_specific_validators(self) -> None:
        db = self.agent.execute(
            {
                "docs_cd": "DB",
                "agent_outputs": {
                    "data_structure_design_agent": {"db_design_json": {"tables": []}}
                },
            }
        )
        arch = self.agent.execute(
            {
                "docs_cd": "ARCH",
                "agent_outputs": {
                    "architecture_analysis_agent": {
                        "architecture_structure_json": {},
                        "architecture_document_json": {},
                    }
                },
            }
        )

        self.assertEqual(_failure(db, "DB_SCHEMA_ERROR")["target_agent"], "data_structure_design_agent")
        self.assertEqual(_failure(arch, "ARCH_SCHEMA_ERROR")["target_agent"], "architecture_analysis_agent")

    def test_validation_only_stores_its_own_output_in_state(self) -> None:
        state = {"docs_cd": "SRS", "agent_outputs": {}}
        original = copy.deepcopy(state)
        result = self.agent.execute(state)
        self.assertEqual(state["agent_outputs"]["validation_agent"], result)
        self.assertNotIn("validation_result", state)
        self.assertEqual(original["docs_cd"], state["docs_cd"])

    def test_top_level_status_matches_validation_status(self) -> None:
        result = self.agent.execute({"docs_cd": "SRS", "agent_outputs": {}})
        self.assertEqual(result["status"], result["validation_result"]["validation_status"])

    def test_ts_quality_traceability_failures_return_replan_targets(self) -> None:
        result = self.agent.execute(
            {
                "docs_cd": "TS",
                "agent_outputs": {
                    "document_merge_agent": {
                        "integrated_requirement_json_list": [
                            {"req_id": "REQ-1", "requirement_type": "기능"}
                        ],
                        "reference_interface_json_list": [{"screen_id": "SCR-1"}],
                    },
                    "test_scenario_generation_agent": {
                        "integrated_test_scenario_json": {
                            "scenario_json_list": [{"scenario_id": "SC-1", "source_requirement_ids": []}],
                            "test_case_json_list": [{"test_case_id": "TC-1", "case_type": "NORMAL"}],
                            "step_json_list": [
                                {
                                    "step_id": "STEP-1",
                                    "test_case_id": "TC-1",
                                    "step_no": 1,
                                    "처리내용": "실행",
                                    "시험항목": "시험",
                                    "사전조건": "조건",
                                    "입력값": "입력",
                                    "예상결과": "결과",
                                    "화면ID": "SCR-X",
                                }
                            ],
                        }
                    },
                },
            }
        )
        self.assertEqual(_failure(result, "TS_REQUIREMENT_COVERAGE_MISSING")["target_agent"], "test_scenario_generation_agent")
        self.assertEqual(_failure(result, "TS_INTERFACE_MAPPING_MISSING")["target_agent"], "test_scenario_generation_agent")
        self.assertEqual(_failure(result, "TS_EXCEPTION_CASE_MISSING")["target_agent"], "test_scenario_generation_agent")

    def test_erd_db_arch_detailed_rules_are_present(self) -> None:
        erd = self.agent.execute(
            {
                "docs_cd": "ERD",
                "agent_outputs": {
                    "data_structure_design_agent": {
                        "erd_entity_json": {
                            "tables": [
                                {
                                    "table_id": "T1",
                                    "logical_name": "사용자",
                                    "physical_name": "Bad Name",
                                    "columns": [{"column_id": "C1", "logical_name": "ID", "physical_name": "Bad ID", "data_type": "INT", "nullable": False, "constraints": ["PK"]}],
                                }
                            ],
                            "relationships": [{"relationship_id": "R1", "parent_table": "missing", "child_table": "Bad Name"}],
                        },
                        "erd_mermaid_json": {"entities": [{"name": "Bad Name"}]},
                    },
                    "mermaid_generation_agent": {"mermaid_code": "erDiagram", "mermaid_image_path": "erd.png"},
                },
            }
        )
        arch = self.agent.execute(
            {
                "docs_cd": "ARCH",
                "agent_outputs": {
                    "architecture_analysis_agent": {
                        "architecture_structure_json": {
                            "overview": "개요",
                            "components": [{"component_id": "A"}, {"component_id": "B"}],
                            "relations": [{"source": "A", "target": "A"}],
                            "layers": ["app"],
                            "deployment_environment": "cloud",
                        },
                        "architecture_document_json": {"overview": "개요"},
                    },
                    "mermaid_generation_agent": {"mermaid_code": "flowchart TD", "mermaid_image_path": "arch.png"},
                },
            }
        )
        self.assertEqual(_failure(erd, "ERD_FK_INVALID")["target_agent"], "data_structure_design_agent")
        self.assertEqual(_failure(erd, "ERD_STANDARD_NAMING_ERROR")["target_agent"], "data_structure_design_agent")
        self.assertEqual(_failure(arch, "ARCH_COMPONENT_ISOLATED")["target_agent"], "architecture_analysis_agent")


def _failure(result, failure_type):
    return next(
        check
        for check in result["validation_result"]["checks"]
        if check["failure_type"] == failure_type
    )


if __name__ == "__main__":
    unittest.main()
