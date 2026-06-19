# 산출물 생성 Supervisor를 실행하는 워크플로우 노드입니다.

from database.repositories.architecture_config_repository import (
    ArchitectureConfigRepository,
)
from database.session import SessionLocal
from supervisor.generation_supervisor import run_generation_supervisor
from supervisor.registry.agent_registry import build_default_agent_registry
from workflow.state import WorkflowState


def generation_supervisor_node(state: WorkflowState) -> WorkflowState:
    session = SessionLocal()
    try:
        registry = build_default_agent_registry(
            architecture_config_repository=ArchitectureConfigRepository(session),
        )
        return run_generation_supervisor(state, registry)
    finally:
        session.close()
