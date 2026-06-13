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

    def test_arch_builds_flowchart(self) -> None:
        result = MermaidGenerationAgent(
            renderer=lambda code, **kwargs: success_result(
                {"mermaid_file_path": "arch.mmd", "mermaid_image_path": "arch.png"}
            )
        ).execute(_arch_state())

        self.assertTrue(result["mermaid_code"].startswith("flowchart TD"))
        self.assertIn("WEB --> API", result["mermaid_code"])

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


if __name__ == "__main__":
    unittest.main()
