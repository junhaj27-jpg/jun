import unittest

from agents.mermaid_generation.agent import MermaidGenerationAgent
from tools.result import error_result, success_result


class FakeRepairLLM:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, **kwargs):
        self.calls += 1
        return success_result({"mermaid_code": "flowchart TD\n    WEB[Web] --> API[API]"})


class MermaidGenerationAgentTest(unittest.TestCase):
    def test_erd_builds_code_and_stores_render_paths(self) -> None:
        codes = []

        def renderer(code, **kwargs):
            codes.append(code)
            return success_result(
                {
                    "mermaid_file_path": "storage/mermaid/erd_diagram.mmd",
                    "mermaid_image_path": "storage/mermaid/erd_diagram.png",
                }
            )

        state = _erd_state()
        result = MermaidGenerationAgent(renderer=renderer).execute(state)

        self.assertEqual(result["status"], "SUCCESS")
        self.assertTrue(result["mermaid_code"].startswith("erDiagram"))
        self.assertIn("tbl_user", result["mermaid_code"])
        self.assertEqual(result["mermaid_image_path"], "storage/mermaid/erd_diagram.png")
        self.assertIs(state["agent_outputs"]["mermaid_generation_agent"], result)
        self.assertNotIn("mermaid_code", state)
        self.assertEqual(len(codes), 1)
        self.assertTrue(codes[0].startswith("erDiagram"))
        self.assertIn("tbl_user {", codes[0])

    def test_arch_builds_flowchart(self) -> None:
        result = MermaidGenerationAgent(
            renderer=lambda code, **kwargs: success_result(
                {"mermaid_file_path": "arch.mmd", "mermaid_image_path": "arch.png"}
            )
        ).execute(_arch_state())

        self.assertTrue(result["mermaid_code"].startswith("flowchart TD"))
        self.assertIn("WEB --> API", result["mermaid_code"])

    def test_arch_uses_component_ids_layers_and_sanitizes_labels(self) -> None:
        state = _arch_state()
        state["agent_outputs"]["architecture_analysis_agent"]["architecture_structure_json"]["layers"] = [
            {"name": "AI/LLM Layer", "component_ids": ["WEB", "API"]}
        ]
        state["agent_outputs"]["architecture_analysis_agent"]["architecture_structure_json"]["relations"] = [
            {"source": "WEB", "target": "API", "description": "API 호출(HTTPS)"}
        ]
        result = MermaidGenerationAgent(
            renderer=lambda code, **kwargs: success_result(
                {"mermaid_file_path": "arch.mmd", "mermaid_image_path": "arch.png"}
            )
        ).execute(state)

        self.assertIn("subgraph AI_LLM_Layer[AI/LLM Layer]", result["mermaid_code"])
        self.assertIn("direction TB", result["mermaid_code"])
        self.assertIn("WEB[Web Client]", result["mermaid_code"])
        self.assertIn("WEB -->|API 호출HTTPS| API", result["mermaid_code"])

    def test_erd_sanitizes_table_column_and_relation_identifiers(self) -> None:
        state = _erd_state()
        state["agent_outputs"]["data_structure_design_agent"]["erd_mermaid_json"] = {
            "entities": [
                {
                    "name": "tbl user",
                    "columns": [
                        {
                            "physical_name": "user id",
                            "data_type": "VARCHAR(100)",
                            "constraints": ["PK"],
                        }
                    ],
                },
                {"name": "2docs", "columns": [{"physical_name": "docs sn"}]},
            ],
            "relationships": [{"parent_table": "tbl user", "child_table": "2docs", "description": "creates()"}],
        }
        result = MermaidGenerationAgent(
            renderer=lambda code, **kwargs: success_result(
                {"mermaid_file_path": "erd.mmd", "mermaid_image_path": "erd.png"}
            )
        ).execute(state)

        self.assertIn("tbl_user {", result["mermaid_code"])
        self.assertIn("VARCHAR_100 user_id PK", result["mermaid_code"])
        self.assertIn("t_2docs {", result["mermaid_code"])
        self.assertIn("tbl_user ||--o{ t_2docs : references", result["mermaid_code"])

    def test_erd_renders_connected_components_as_multiple_groups(self) -> None:
        calls = []

        def renderer(code, **kwargs):
            calls.append({"code": code, "file_stem": kwargs["file_stem"]})
            return success_result(
                {
                    "mermaid_file_path": f"storage/mermaid/{kwargs['file_stem']}.mmd",
                    "mermaid_image_path": f"storage/mermaid/{kwargs['file_stem']}.png",
                }
            )

        state = _erd_state()
        state["agent_outputs"]["data_structure_design_agent"]["erd_mermaid_json"] = {
            "entities": [
                _erd_entity("tbl_a"),
                _erd_entity("tbl_b"),
                _erd_entity("tbl_c"),
                _erd_entity("tbl_d"),
                _erd_entity("tbl_e"),
                _erd_entity("tbl_f"),
            ],
            "relationships": [
                {"parent_table": "tbl_a", "child_table": "tbl_b"},
                {"parent_table": "tbl_b", "child_table": "tbl_c"},
                {"parent_table": "tbl_d", "child_table": "tbl_e"},
            ],
        }

        result = MermaidGenerationAgent(renderer=renderer).execute(state)

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["mermaid_image_paths"], [
            "storage/mermaid/erd_group_1.png",
            "storage/mermaid/erd_orphan_2.png",
        ])
        self.assertEqual([call["file_stem"] for call in calls], ["erd_group_1", "erd_orphan_2"])
        self.assertEqual(len(result["mermaid_groups"]), 2)
        self.assertTrue(all("tbl_f" not in call["code"] for call in calls if call["file_stem"] == "erd_group_1"))
        self.assertTrue(any("tbl_f" in call["code"] for call in calls if call["file_stem"] == "erd_orphan_2"))
        self.assertTrue(any(call["code"].startswith("erDiagram") for call in calls if call["file_stem"] == "erd_orphan_2"))

    def test_erd_groups_orphans_by_four_and_does_not_duplicate_tables(self) -> None:
        calls = []

        def renderer(code, **kwargs):
            calls.append({"code": code, "file_stem": kwargs["file_stem"]})
            return success_result(
                {
                    "mermaid_file_path": f"storage/mermaid/{kwargs['file_stem']}.mmd",
                    "mermaid_image_path": f"storage/mermaid/{kwargs['file_stem']}.png",
                }
            )

        state = _erd_state()
        state["agent_outputs"]["data_structure_design_agent"]["erd_mermaid_json"] = {
            "entities": [_erd_entity(f"tbl_{index}") for index in range(1, 12)],
            "relationships": [
                {"parent_table": "tbl_1", "child_table": "tbl_2"},
                {"parent_table": "tbl_2", "child_table": "tbl_3"},
            ],
        }

        result = MermaidGenerationAgent(renderer=renderer).execute(state)

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["coverage_result"]["missing_table_count"], 0)
        rendered_names = [
            table_name
            for group in result["mermaid_groups"]
            for table_name in group["table_names"]
        ]
        self.assertEqual(len(rendered_names), len(set(rendered_names)))
        self.assertEqual(len(set(rendered_names)), 11)
        orphan_groups = [
            group for group in result["mermaid_groups"] if group["group_type"] == "orphan"
        ]
        self.assertEqual([len(group["table_names"]) for group in orphan_groups], [4, 4])
        self.assertTrue(all(call["file_stem"].startswith(("erd_group_", "erd_orphan_")) for call in calls))

    def test_orphan_erd_uses_erd_style_and_limits_columns_to_four(self) -> None:
        calls = []

        def renderer(code, **kwargs):
            calls.append({"code": code, "file_stem": kwargs["file_stem"]})
            return success_result(
                {
                    "mermaid_file_path": f"storage/mermaid/{kwargs['file_stem']}.mmd",
                    "mermaid_image_path": f"storage/mermaid/{kwargs['file_stem']}.png",
                }
            )

        state = _erd_state()
        state["agent_outputs"]["data_structure_design_agent"]["erd_mermaid_json"] = {
            "entities": [_sample_table(f"tbl_ref_{index}", table_type="CODE") for index in range(1, 5)],
            "relationships": [],
        }

        result = MermaidGenerationAgent(renderer=renderer).execute(state)

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(len(result["mermaid_groups"]), 1)
        self.assertEqual(result["mermaid_groups"][0]["group_type"], "orphan")
        self.assertEqual(len(result["mermaid_groups"][0]["table_names"]), 4)
        code = calls[0]["code"]
        self.assertTrue(code.startswith("erDiagram"))
        self.assertNotIn("flowchart", code)
        self.assertIn("tbl_ref_1 {", code)
        self.assertIn("ref_1_sn PK", code)
        self.assertIn("ref_1_nm", code)
        self.assertIn("crt_dt", code)
        self.assertNotIn("udt_dt", code)

    def test_erd_grouping_is_domain_agnostic_for_ai_business_and_orphan_samples(self) -> None:
        samples = [_ai_platform_sample(), _business_system_sample(), _many_orphan_sample()]
        for sample in samples:
            with self.subTest(sample=sample["name"]):
                calls = []

                def renderer(code, **kwargs):
                    calls.append({"code": code, "kwargs": kwargs})
                    return success_result(
                        {
                            "mermaid_file_path": f"storage/mermaid/{kwargs['file_stem']}.mmd",
                            "mermaid_image_path": f"storage/mermaid/{kwargs['file_stem']}.png",
                            "render_options": {
                                "width": kwargs.get("render_width"),
                                "height": kwargs.get("render_height"),
                                "scale": kwargs.get("render_scale"),
                            },
                        }
                    )

                state = _erd_state()
                state["agent_outputs"]["data_structure_design_agent"]["erd_mermaid_json"] = sample["erd"]
                result = MermaidGenerationAgent(renderer=renderer).execute(state)

                self.assertEqual(result["status"], "SUCCESS")
                self.assertEqual(result["coverage_result"]["missing_table_count"], 0)
                rendered_names = [
                    table_name
                    for group in result["mermaid_groups"]
                    for table_name in group["table_names"]
                ]
                self.assertEqual(set(rendered_names), sample["expected_tables"])
                self.assertEqual(len(rendered_names), len(set(rendered_names)))
                self.assertTrue(all(call["kwargs"].get("render_scale") == 3 for call in calls))
                orphan_calls = [call for call in calls if call["kwargs"]["file_stem"].startswith("erd_orphan_")]
                self.assertTrue(all(call["code"].startswith("erDiagram") for call in orphan_calls))

    def test_renderer_failure_uses_rule_then_llm_repair(self) -> None:
        calls = []
        llm = FakeRepairLLM()

        def renderer(code, **kwargs):
            calls.append(code)
            if len(calls) < 3:
                return error_result(
                    "MERMAID_RENDER_FAILED",
                    "syntax error",
                    {"mermaid_file_path": "failed.mmd"},
                )
            return success_result(
                {"mermaid_file_path": "fixed.mmd", "mermaid_image_path": "fixed.png"}
            )

        state = _arch_state()
        state["etc"] = {"debug": True}
        result = MermaidGenerationAgent(llm_client=llm, renderer=renderer).execute(state)

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(len(calls), 3)
        self.assertEqual(llm.calls, 1)
        self.assertEqual(len(result["debug"]["render_attempts"]), 3)
        self.assertEqual(result["warnings"][0]["code"], "MERMAID_REPAIRED")

    def test_three_render_failures_return_document_failure_type(self) -> None:
        result = MermaidGenerationAgent(
            renderer=lambda code, **kwargs: error_result(
                "MERMAID_RENDER_FAILED",
                "syntax error",
                {"mermaid_file_path": "failed.mmd"},
            )
        ).execute(_erd_state())

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["failure_type"], "ERD_MERMAID_RENDER_FAILED")
        self.assertEqual(result["mermaid_file_path"], "failed.mmd")

    def test_invalid_input_fails_before_render(self) -> None:
        result = MermaidGenerationAgent().execute(
            {"docs_cd": "ARCH", "agent_outputs": {"architecture_analysis_agent": {}}}
        )
        self.assertEqual(result["failure_type"], "ARCH_MERMAID_INPUT_INVALID")


def _erd_state():
    return {
        "docs_cd": "ERD",
        "agent_outputs": {
            "data_structure_design_agent": {
                "erd_mermaid_json": {
                    "entities": [
                        {
                            "name": "tbl_user",
                            "columns": [
                                {
                                    "physical_name": "user_sn",
                                    "data_type": "BIGINT",
                                    "constraints": ["PK"],
                                }
                            ],
                        }
                    ],
                    "relationships": [],
                }
            }
        },
    }


def _arch_state():
    return {
        "docs_cd": "ARCH",
        "agent_outputs": {
            "architecture_analysis_agent": {
                "architecture_structure_json": {
                    "components": [
                        {"component_id": "WEB", "name": "Web Client"},
                        {"component_id": "API", "name": "FastAPI Server"},
                    ],
                    "relations": [{"source": "WEB", "target": "API"}],
                    "layers": [],
                }
            }
        },
    }


def _erd_entity(name: str):
    return {
        "name": name,
        "domain_group": "COMMON",
        "importance_score": 50,
        "relation_count": 1,
        "columns": [{"physical_name": f"{name.removeprefix('tbl_')}_sn", "data_type": "BIGINT", "constraints": ["PK"]}],
    }


def _ai_platform_sample():
    tables = [
        _sample_table("tbl_model", "AI"),
        _sample_table("tbl_prompt", "AI"),
        _sample_table("tbl_dataset", "DATA"),
        _sample_table("tbl_inference_log", "LOG"),
        _sample_table("tbl_code", "CODE"),
    ]
    relationships = [
        {"parent_table": "tbl_model", "child_table": "tbl_prompt"},
        {"parent_table": "tbl_dataset", "child_table": "tbl_model"},
        {"parent_table": "tbl_model", "child_table": "tbl_inference_log"},
    ]
    return {
        "name": "ai_platform",
        "erd": {"tables": tables, "relationships": relationships},
        "expected_tables": {table["table_name"] for table in tables},
    }


def _business_system_sample():
    tables = [
        _sample_table("tbl_customer", table_type="MASTER"),
        _sample_table("tbl_order", table_type="MASTER"),
        _sample_table("tbl_order_detail", table_type="DETAIL"),
        _sample_table("tbl_payment", table_type="HISTORY"),
        _sample_table("tbl_approval", table_type="APPROVAL"),
    ]
    relationships = [
        {"parent_table": "tbl_customer", "child_table": "tbl_order"},
        {"parent_table": "tbl_order", "child_table": "tbl_order_detail"},
        {"parent_table": "tbl_order", "child_table": "tbl_payment"},
        {"parent_table": "tbl_order", "child_table": "tbl_approval"},
    ]
    return {
        "name": "business_system_without_domain_group",
        "erd": {"tables": tables, "relationships": relationships},
        "expected_tables": {table["table_name"] for table in tables},
    }


def _many_orphan_sample():
    tables = [_sample_table(f"tbl_ref_{index}", table_type="CODE") for index in range(1, 10)]
    return {
        "name": "many_orphans",
        "erd": {"tables": tables, "relationships": []},
        "expected_tables": {table["table_name"] for table in tables},
    }


def _sample_table(name: str, domain_group: str | None = None, table_type: str = "MASTER"):
    table = {
        "table_name": name,
        "table_type": table_type,
        "columns": [
            {"physical_name": f"{name.removeprefix('tbl_')}_sn", "data_type": "BIGINT", "constraints": ["PK"]},
            {"physical_name": f"{name.removeprefix('tbl_')}_nm", "data_type": "VARCHAR(200)", "constraints": []},
            {"physical_name": "use_yn", "data_type": "CHAR(1)", "constraints": []},
            {"physical_name": "crt_dt", "data_type": "DATETIME", "constraints": []},
            {"physical_name": "udt_dt", "data_type": "DATETIME", "constraints": []},
        ],
    }
    if domain_group:
        table["domain_group"] = domain_group
    return table


if __name__ == "__main__":
    unittest.main()
