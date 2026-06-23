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
    if docs_cd == "ERD" and "data_structure_design_agent" in agents:
        data_index = agents.index("data_structure_design_agent")
        if "mermaid_generation_agent" not in agents:
            agents.insert(data_index + 1, "mermaid_generation_agent")
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
        check_failure_type = str(check.get("failure_type") or "")
        check_scope = _scope_values(check.get("target_scope"))
        for mapped_agent in get_failure_agents(check_failure_type):
            _add_target(agents, metadata, mapped_agent, check_scope)
        check_target_agent = check.get("target_agent")
        if check_target_agent:
            _add_target(
                agents,
                metadata,
                str(check_target_agent),
                check_scope,
            )

    # failed_checks가 없거나 일부 check에 target 정보가 없어도 대표 실패 유형의
    # 하네스 매핑은 항상 반영합니다.
    for mapped_agent in get_failure_agents(failure_type):
        _add_target(agents, metadata, mapped_agent, _scope_values(target_scope))
    if target_agent:
        _add_target(agents, metadata, target_agent, _scope_values(target_scope))

    return list(dict.fromkeys(agents)), metadata


def _add_target(
    agents: list[str],
    metadata: dict[str, dict[str, Any]],
    agent_name: str,
    scope: list[str],
) -> None:
    if not agent_name:
        return
    agents.append(agent_name)
    if not scope:
        return
    current = metadata.setdefault(agent_name, {}).setdefault("retry_scope", [])
    current.extend(value for value in scope if value not in current)


def _scope_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if value in (None, ""):
        return []
    return [str(value)]


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
