# Agent 이름과 실행 callable을 매핑하고 조회합니다.

from collections.abc import Callable
from typing import Any

from agents.architecture_analysis.agent import ArchitectureAnalysisAgent
from agents.data_structure_design.agent import DataStructureDesignAgent
from agents.document_merge.agent import DocumentMergeAgent
from agents.image_analysis.agent import ImageAnalysisAgent
from agents.mermaid_generation.agent import MermaidGenerationAgent
from agents.requirement_generation.agent import RequirementGenerationAgent
from agents.test_scenario.agent import TestScenarioGenerationAgent
from agents.validation.agent import ValidationAgent
from workflow.state import WorkflowState


AgentCallable = Callable[[WorkflowState], dict[str, Any]]


class AgentRegistry:
    def __init__(self, agents: dict[str, AgentCallable] | None = None) -> None:
        self._agents: dict[str, AgentCallable] = dict(agents or {})

    def register(self, agent_name: str, agent: AgentCallable) -> None:
        self._agents[agent_name] = agent

    def get(self, agent_name: str) -> AgentCallable:
        try:
            return self._agents[agent_name]
        except KeyError as exc:
            raise KeyError(f"등록되지 않은 Agent입니다: {agent_name}") from exc

    def run(self, agent_name: str, state: WorkflowState) -> dict[str, Any]:
        return self.get(agent_name)(state)

default_agent_registry = AgentRegistry(
    {
        "document_merge_agent": DocumentMergeAgent().execute,
        "requirement_generation_agent": RequirementGenerationAgent().execute,
        "image_analysis_agent": ImageAnalysisAgent().execute,
        "test_scenario_generation_agent": TestScenarioGenerationAgent().execute,
        "architecture_analysis_agent": ArchitectureAnalysisAgent().execute,
        "data_structure_design_agent": DataStructureDesignAgent().execute,
        "mermaid_generation_agent": MermaidGenerationAgent().execute,
        "validation_agent": ValidationAgent().execute,
    }
)
