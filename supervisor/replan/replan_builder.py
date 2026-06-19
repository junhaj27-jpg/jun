# 실패 결과를 기반으로 재실행 계획을 생성합니다.

from typing import Any

from supervisor.plan.plan_builder import build_plan
from supervisor.replan.failure_agent_mapper import get_failure_agents


def build_replan(
    docs_cd: str,
    udt_yn: str,
    failure_type: str,
    *,
    current_round: int,
    max_round: int,
    target_agent: str | None = None,
    target_scope: list[str] | None = None,
    failed_checks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    target_agents, step_metadata = _extract_targets(
        failure_type,
        target_agent=target_agent,
        target_scope=target_scope,
        failed_checks=failed_checks,
    )
    if not target_agents:
        target_agents = _infer_agents_from_failure_type(failure_type)

    agents = list(target_agents)
    agents.append("validation_agent")
    agents = list(dict.fromkeys(agents))
    if agents[-1] != "validation_agent":
        agents.append("validation_agent")

    return build_plan(
        docs_cd,
        udt_yn,
        round_number=current_round + 1,
        max_round=max_round,
        agents=agents,
        replan_reason=failure_type,
        require_document_merge_first=False,
        step_metadata=step_metadata,
    )


def _extract_targets(
    failure_type: str,
    *,
    target_agent: str | None,
    target_scope: list[str] | None,
    failed_checks: list[dict[str, Any]] | None,
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    agents: list[str] = []
    metadata: dict[str, dict[str, Any]] = {}

    checks = failed_checks or []
    for check in checks:
        check_target_agent = check.get("target_agent")
        if check_target_agent:
            agent_name = str(check_target_agent)
            agents.append(agent_name)
            check_scope = check.get("target_scope") or []
            if check_scope:
                metadata.setdefault(agent_name, {})["retry_scope"] = list(check_scope)

    if target_agent:
        agents.append(target_agent)
        if target_scope:
            metadata.setdefault(target_agent, {})["retry_scope"] = list(target_scope)

    if not agents:
        agents = get_failure_agents(failure_type)

    return list(dict.fromkeys(agents)), metadata


def _infer_agents_from_failure_type(failure_type: str) -> list[str]:
    normalized = failure_type.upper()
    if "DOCUMENT_MERGE" in normalized:
        return ["document_merge_agent"]
    if "VALIDATION" in normalized:
        return []
    if "REQUIREMENT" in normalized or "SRS" in normalized:
        return ["requirement_generation_agent"]
    if "INTERFACE" in normalized or "IMAGE" in normalized:
        return ["image_analysis_agent"]
    if normalized.startswith("TS_") or "TEST_SCENARIO" in normalized:
        return ["test_scenario_generation_agent"]
    if "MERMAID" in normalized:
        return ["mermaid_generation_agent"]
    if "ARCH" in normalized:
        return ["architecture_analysis_agent"]
    if "ERD" in normalized or "DB" in normalized or "DATA_STRUCTURE" in normalized:
        return ["data_structure_design_agent"]
    return []
