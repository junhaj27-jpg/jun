# 문서 코드와 수정 여부를 기준으로 Agent 실행 계획을 생성합니다.

from typing import Any

from supervisor.plan.execution_harness import get_execution_agents
from supervisor.plan.required_output_harness import get_required_output_keys


def build_plan(
    docs_cd: str,
    udt_yn: str,
    *,
    round_number: int = 1,
    max_round: int = 3,
    agents: list[str] | None = None,
    replan_reason: str | None = None,
) -> dict[str, Any]:
    agent_names = agents or get_execution_agents(docs_cd, udt_yn)
    if not agent_names or agent_names[0] != "document_merge_agent":
        raise ValueError("document_merge_agent는 항상 첫 번째 step이어야 합니다.")
    if agent_names[-1] != "validation_agent":
        raise ValueError("validation_agent는 항상 마지막 step이어야 합니다.")

    plan: dict[str, Any] = {
        "round": round_number,
        "max_round": max_round,
        "docs_cd": docs_cd,
        "udt_yn": udt_yn,
        "steps": [
            {
                "step": index,
                "agent": agent_name,
                "status": "PENDING",
                "required_output_keys": get_required_output_keys(
                    agent_name, docs_cd, udt_yn
                ),
            }
            for index, agent_name in enumerate(agent_names, start=1)
        ],
    }
    if replan_reason:
        plan["replan_reason"] = replan_reason
    return plan
