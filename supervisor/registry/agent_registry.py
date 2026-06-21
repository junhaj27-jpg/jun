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
from tools.llm.llm_client import LLMClient
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


def _debug_enabled(state: WorkflowState) -> bool:
    return bool((state.get("etc") or {}).get("debug"))


def _make_llm_client() -> LLMClient | None:
    """OpenAI 호환 LLM 클라이언트를 생성합니다.

    설정/환경 문제로 클라이언트 생성이 실패해도 Supervisor 전체가 죽지 않도록
    None을 반환하고, 각 Agent는 기존 fallback 로직으로 동작합니다.
    """

    try:
        return LLMClient()
    except Exception:
        return None


def _trace_wrapper(agent_name: str, agent: AgentCallable) -> AgentCallable:
    """debug=true일 때만 ARCH 실행 경로를 추적하는 얇은 wrapper입니다."""

    def wrapped(state: WorkflowState) -> dict[str, Any]:
        if _debug_enabled(state) and str(state.get("docs_cd", "")).upper() == "ARCH":
            print(f"[ARCH_TRACE][registry] running agent: {agent_name}")
            print("[ARCH_TRACE][registry] docs_cd:", state.get("docs_cd"))
            print("[ARCH_TRACE][registry] udt_yn:", state.get("udt_yn"))
            print("[ARCH_TRACE][registry] state keys:", list(state.keys()))
            print("[ARCH_TRACE][registry] has existing_output_path:", bool(state.get("existing_output_path")))
            print("[ARCH_TRACE][registry] input_file_paths:", state.get("input_file_paths"))
        output = agent(state)
        if _debug_enabled(state) and str(state.get("docs_cd", "")).upper() == "ARCH":
            print(f"[ARCH_TRACE][registry] output status({agent_name}):", output.get("status") if isinstance(output, dict) else None)
            print(f"[ARCH_TRACE][registry] output keys({agent_name}):", list(output.keys()) if isinstance(output, dict) else None)
        return output

    return wrapped


def build_default_agent_registry(
    *,
    architecture_config_repository: Any | None = None,
    llm_client: LLMClient | None = None,
) -> AgentRegistry:
    """기본 Agent Registry를 구성합니다.

    CORE의 최신 registry 구조와 백업본의 ARCH LLM/debug 연결을 함께 반영합니다.
    - `architecture_config_repository` 주입 유지
    - ARCH 분석/문서 병합/Mermaid 보정에서 LLM 사용 가능
    - debug=true일 때만 ARCH_TRACE 출력
    """

    shared_llm_client = llm_client if llm_client is not None else _make_llm_client()
    agents: dict[str, AgentCallable] = {
        "document_merge_agent": DocumentMergeAgent(llm_client=shared_llm_client).execute,
        "requirement_generation_agent": RequirementGenerationAgent(llm_client=shared_llm_client).execute,
        "image_analysis_agent": ImageAnalysisAgent().execute,
        "test_scenario_generation_agent": TestScenarioGenerationAgent(llm_client=shared_llm_client).execute,
        "architecture_analysis_agent": ArchitectureAnalysisAgent(
            llm_client=shared_llm_client,
            architecture_config_repository=architecture_config_repository,
        ).execute,
        "data_structure_design_agent": DataStructureDesignAgent(llm_client=shared_llm_client).execute,
        "mermaid_generation_agent": MermaidGenerationAgent(llm_client=shared_llm_client).execute,
        "validation_agent": ValidationAgent().execute,
    }
    return AgentRegistry({name: _trace_wrapper(name, agent) for name, agent in agents.items()})


default_agent_registry = build_default_agent_registry()
