from typing import Any

from config.logging_config import get_logger
from config.logging_context import bind_state_log_extra
from supervisor.evaluate.evaluator import evaluate_step
from supervisor.plan.plan_builder import build_plan
from supervisor.reduce.reduce_builder import reduce_outputs
from supervisor.registry.agent_registry import AgentRegistry, default_agent_registry
from supervisor.replan.replan_builder import build_replan
from supervisor.replan.retry_policy import can_replan, can_retry_step, is_terminal_failure
from workflow.state import WorkflowState


logger = get_logger("supervisor.generation_supervisor")


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
        logger.info(
            "Initial supervisor plan built",
            extra=bind_state_log_extra(state, "supervisor_plan_built", round=1),
        )

        while True:
            state["current_round"] = state["execution_plan"]["round"]
            logger.info(
                "Supervisor round started round=%s",
                state["current_round"],
                extra=bind_state_log_extra(
                    state,
                    "supervisor_round_start",
                    round=state["current_round"],
                ),
            )
            failure = self._execute_plan(state)
            if failure is None:
                logger.info(
                    "Supervisor reducing agent outputs",
                    extra=bind_state_log_extra(
                        state,
                        "supervisor_reduce_outputs",
                        round=state["current_round"],
                    ),
                )
                return reduce_outputs(state)
            if failure.get("action") == "END":
                return self._mark_failed(state, failure)
            if not can_replan(state["current_round"], state["max_round"]):
                return self._mark_failed(state, failure)
            logger.warning(
                "Supervisor replanning failure_type=%s",
                failure.get("failure_type"),
                extra=bind_state_log_extra(
                    state,
                    "supervisor_replan",
                    round=state["current_round"],
                    agent=failure.get("agent"),
                ),
            )
            state["execution_plan"] = build_replan(
                state["docs_cd"],
                state["udt_yn"],
                str(failure["failure_type"]),
                current_round=state["current_round"],
                max_round=state["max_round"],
                target_agent=failure.get("target_agent"),
                target_scope=failure.get("target_scope"),
                failed_checks=failure.get("failed_checks"),
            )

    def _execute_plan(self, state: WorkflowState) -> dict[str, Any] | None:
        for step in state["execution_plan"]["steps"]:
            agent_name = step["agent"]
            retry_count = 0
            while True:
                step["status"] = "RUNNING"
                step["retry_count"] = retry_count
                logger.info(
                    "Supervisor step started agent=%s retry=%s",
                    agent_name,
                    retry_count,
                    extra=bind_state_log_extra(
                        state,
                        "supervisor_step_start",
                        round=state["current_round"],
                        agent=agent_name,
                        step=step.get("step"),
                    ),
                )
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
                if evaluation["success"]:
                    step["status"] = "DONE"
                    logger.info(
                        "Supervisor step completed agent=%s",
                        agent_name,
                        extra=bind_state_log_extra(
                            state,
                            "supervisor_step_done",
                            round=state["current_round"],
                            agent=agent_name,
                            step=step.get("step"),
                        ),
                    )
                    break

                evaluation = {
                    **evaluation,
                    "agent": agent_name,
                    "step": step.get("step"),
                }
                if evaluation.get("action") != "REPLAN" and is_terminal_failure(
                    str(evaluation.get("failure_type") or "")
                ):
                    step["status"] = "FAILED"
                    evaluation["action"] = "END"
                    return evaluation
                if can_retry_step(agent_name, evaluation, retry_count):
                    retry_count += 1
                    step["status"] = "RETRY"
                    step["retry_count"] = retry_count
                    logger.warning(
                        "Supervisor step retry agent=%s retry=%s",
                        agent_name,
                        retry_count,
                        extra=bind_state_log_extra(
                            state,
                            "supervisor_step_retry",
                            round=state["current_round"],
                            agent=agent_name,
                            step=step.get("step"),
                        ),
                    )
                    continue
                step["status"] = "FAILED"
                return evaluation
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
        logger.error(
            "Supervisor failed failure_type=%s",
            failure.get("failure_type") or "SUPERVISOR_FAILED",
            extra=bind_state_log_extra(
                state,
                "supervisor_failed",
                round=state.get("current_round"),
                agent=failure.get("agent"),
                step=failure.get("step"),
            ),
        )
        state["errors"].append(
            {
                "code": failure.get("failure_type") or "SUPERVISOR_FAILED",
                "message": failure.get("message") or "Supervisor execution failed.",
            }
        )
        return state


def run_generation_supervisor(
    state: WorkflowState,
    agent_registry: AgentRegistry | None = None,
) -> WorkflowState:
    return GenerationSupervisor(agent_registry).run(state)
