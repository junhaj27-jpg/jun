# 산출물 생성의 계획, 평가, 재계획 및 결과 취합 과정을 총괄합니다.

from typing import Any

from supervisor.evaluate.evaluator import evaluate_step
from supervisor.plan.plan_builder import build_plan
from supervisor.reduce.reduce_builder import reduce_outputs
from supervisor.registry.agent_registry import AgentRegistry, default_agent_registry
from supervisor.replan.replan_builder import build_replan
from supervisor.replan.retry_policy import can_replan
from workflow.state import WorkflowState


class GenerationSupervisor:
    def __init__(self, agent_registry: AgentRegistry | None = None) -> None:
        self.agent_registry = agent_registry or default_agent_registry

    def run(self, state: WorkflowState) -> WorkflowState:
        self._prepare_state(state)
        state["execution_plan"] = build_plan(
            state["docs_cd"],
            state["udt_yn"],
            round_number=1,
            max_round=state["max_round"],
        )

        while True:
            state["current_round"] = state["execution_plan"]["round"]
            failure = self._execute_plan(state)
            if failure is None:
                return reduce_outputs(state)
            if not can_replan(state["current_round"], state["max_round"]):
                return self._mark_failed(state, failure)
            state["execution_plan"] = build_replan(
                state["docs_cd"],
                state["udt_yn"],
                str(failure["failure_type"]),
                current_round=state["current_round"],
                max_round=state["max_round"],
            )

    def _execute_plan(self, state: WorkflowState) -> dict[str, Any] | None:
        for step in state["execution_plan"]["steps"]:
            agent_name = step["agent"]
            step["status"] = "RUNNING"
            try:
                output = self.agent_registry.run(agent_name, state)
            except Exception as exc:
                output = {
                    "status": "FAILED",
                    "failure_type": f"{agent_name.upper()}_EXECUTION_FAILED",
                    "warnings": [],
                    "errors": [{"message": str(exc)}],
                }

            state["agent_outputs"][agent_name] = output
            if agent_name == "validation_agent":
                state["validation_result"] = output.get("validation_result")

            evaluation = evaluate_step(
                agent_name,
                output,
                step.get("required_output_keys", []),
            )
            if not evaluation["success"]:
                step["status"] = "FAILED"
                return evaluation
            step["status"] = "DONE"
        return None

    @staticmethod
    def _prepare_state(state: WorkflowState) -> None:
        state.setdefault("agent_outputs", {})
        state.setdefault("execution_plan", {})
        state.setdefault("current_round", 0)
        state.setdefault("max_round", 3)
        state.setdefault("warnings", [])
        state.setdefault("errors", [])
        state["status"] = "RUNNING"
        state["next_action"] = "CONTINUE"

    @staticmethod
    def _mark_failed(state: WorkflowState, failure: dict[str, Any]) -> WorkflowState:
        state["status"] = "FAILED"
        state["next_action"] = "END"
        state["errors"].append(
            {
                "code": failure.get("failure_type") or "SUPERVISOR_FAILED",
                "message": failure.get("message") or "Supervisor 실행에 실패했습니다.",
            }
        )
        return state


def run_generation_supervisor(
    state: WorkflowState,
    agent_registry: AgentRegistry | None = None,
) -> WorkflowState:
    return GenerationSupervisor(agent_registry).run(state)
