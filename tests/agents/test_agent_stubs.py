import unittest

from agents.architecture_analysis.agent import ArchitectureAnalysisAgent
from agents.data_structure_design.agent import DataStructureDesignAgent
from agents.document_merge.agent import DocumentMergeAgent
from agents.image_analysis.agent import ImageAnalysisAgent
from agents.mermaid_generation.agent import MermaidGenerationAgent
from agents.requirement_generation.agent import RequirementGenerationAgent
from agents.test_scenario.agent import TestScenarioGenerationAgent
from agents.validation.agent import ValidationAgent
from supervisor.registry.agent_registry import default_agent_registry


class AgentStubsTest(unittest.TestCase):
    def test_document_merge_outputs_follow_mode(self) -> None:
        agent = DocumentMergeAgent()

        created = agent.execute({"docs_cd": "DB", "udt_yn": "N"})
        updated = agent.execute({"docs_cd": "ARCH", "udt_yn": "Y"})

        self.assertEqual(created["status"], "FAILED")
        self.assertEqual(created["failure_type"], "BASE_REQUIREMENT_MISSING")
        self.assertEqual(updated["status"], "FAILED")
        self.assertEqual(updated["failure_type"], "EXISTING_OUTPUT_MISSING")

    def test_architecture_analysis_agent_is_no_longer_an_empty_stub(self) -> None:
        result = ArchitectureAnalysisAgent().execute({"docs_cd": "SRS", "udt_yn": "N"})

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["failure_type"], "ARCHITECTURE_INVALID_DOCS_CD")

    def test_mermaid_generation_agent_is_no_longer_an_empty_stub(self) -> None:
        result = MermaidGenerationAgent().execute({"docs_cd": "DB"})

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["failure_type"], "MERMAID_INVALID_DOCS_CD")

    def test_data_structure_design_agent_is_no_longer_an_empty_stub(self) -> None:
        result = DataStructureDesignAgent().execute({"docs_cd": "SRS", "udt_yn": "N"})

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["failure_type"], "DATA_STRUCTURE_INVALID_MODE")

    def test_test_scenario_agent_is_no_longer_an_empty_stub(self) -> None:
        result = TestScenarioGenerationAgent().execute({"docs_cd": "SRS", "udt_yn": "N"})

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["failure_type"], "TEST_SCENARIO_INVALID_DOCS_CD")

    def test_image_analysis_agent_is_no_longer_an_empty_stub(self) -> None:
        result = ImageAnalysisAgent().execute({"docs_cd": "SRS", "udt_yn": "N"})

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["failure_type"], "IMAGE_ANALYSIS_INVALID_DOCS_CD")

    def test_requirement_generation_agent_is_no_longer_an_empty_stub(self) -> None:
        result = RequirementGenerationAgent().execute({"docs_cd": "SRS", "udt_yn": "N"})

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["failure_type"], "INTEGRATED_REQUIREMENT_MISSING")

    def test_validation_agent_is_no_longer_an_empty_stub(self) -> None:
        result = ValidationAgent().execute({"docs_cd": "SRS", "agent_outputs": {}})

        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["validation_result"]["validation_status"], "FAIL")
        self.assertEqual(
            result["validation_result"]["checks"][0]["failure_type"],
            "SRS_OUTPUT_MISSING",
        )

    def test_default_registry_calls_agent_classes(self) -> None:
        result = default_agent_registry.run(
            "requirement_generation_agent",
            {"docs_cd": "SRS", "udt_yn": "N"},
        )

        self.assertEqual(result["status"], "FAILED")


if __name__ == "__main__":
    unittest.main()
