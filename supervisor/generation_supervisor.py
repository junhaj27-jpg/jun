from typing import Any

from config.logging_config import get_logger
from config.logging_context import bind_state_log_extra
from supervisor.evaluate.evaluator import evaluate_step
from supervisor.plan.plan_builder import build_plan
from supervisor.reduce.reduce_builder import reduce_outputs
from supervisor.registry.agent_registry import AgentRegistry, default_agent_registry
from supervisor.repair import build_repair_instruction
from supervisor.replan.replan_builder import build_replan
from supervisor.replan.retry_policy import can_replan, can_retry_step, is_terminal_failure
from workflow.state import WorkflowState


logger = get_logger("supervisor.generation_supervisor")


class GenerationSupervisor:
    def __init__(self, agent_registry: AgentRegistry | None = None) -> None:
        self.agent_registry = agent_registry or default_agent_registry

    def run(self, state: WorkflowState) -> WorkflowState:
        self._prepare_state(state)
        debug = bool((state.get("etc") or {}).get("debug"))
        if debug and str(state.get("docs_cd", "")).upper() == "ARCH":
            print("[ARCH_TRACE][supervisor.run] file:", __file__)
            print("[ARCH_TRACE][supervisor.run] docs_cd:", state.get("docs_cd"))
            print("[ARCH_TRACE][supervisor.run] udt_yn:", state.get("udt_yn"))
            print("[ARCH_TRACE][supervisor.run] state keys:", list(state.keys()))

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
        if debug and str(state.get("docs_cd", "")).upper() == "ARCH":
            print("[ARCH_TRACE][supervisor.run] execution_plan:", state["execution_plan"])

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
                self._finish_repair(state, "PASS")
                logger.info(
                    "Supervisor reducing agent outputs",
                    extra=bind_state_log_extra(
                        state,
                        "supervisor_reduce_outputs",
                        round=state["current_round"],
                    ),
                )
                if debug and str(state.get("docs_cd", "")).upper() == "ARCH":
                    print("[ARCH_TRACE][supervisor.run] plan success. reducing outputs.")
                    print("[ARCH_TRACE][supervisor.run] agent_outputs keys:", list(state.get("agent_outputs", {}).keys()))
                return reduce_outputs(state)
            if debug and str(state.get("docs_cd", "")).upper() == "ARCH":
                print("[ARCH_TRACE][supervisor.run] failure:", failure)
            if failure.get("action") == "END":
                return self._mark_failed(state, failure)
            if not can_replan(state["current_round"], state["max_round"]):
                self._finish_repair(state, "FAILED")
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
            self._finish_repair(state, "FAILED")
            self._prepare_repair(state, failure)
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
            if debug and str(state.get("docs_cd", "")).upper() == "ARCH":
                print("[ARCH_TRACE][supervisor.run] rebuilt execution_plan:", state["execution_plan"])

    def _execute_plan(self, state: WorkflowState) -> dict[str, Any] | None:
        debug = bool((state.get("etc") or {}).get("debug"))
        for step in state["execution_plan"]["steps"]:
            agent_name = step["agent"]
            retry_count = 0
            while True:
                step["status"] = "RUNNING"
                step["retry_count"] = retry_count
                state["supervisor_decision"] = {
                    "action": "RETRY_AGENT" if state["current_round"] > 1 else "EXECUTE_AGENT",
                    "round": state["current_round"],
                    "agent": agent_name,
                    "failure_type": state["execution_plan"].get("replan_reason"),
                    "target_scope": list(step.get("retry_scope", [])),
                }
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
                if debug and str(state.get("docs_cd", "")).upper() == "ARCH":
                    print("[ARCH_TRACE][supervisor.step] running agent:", agent_name)
                    print("[ARCH_TRACE][supervisor.step] step:", step.get("step"))
                    print("[ARCH_TRACE][supervisor.step] retry_count:", retry_count)
                    print("[ARCH_TRACE][supervisor.step] required_output_keys:", step.get("required_output_keys", []))
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
                if debug and str(state.get("docs_cd", "")).upper() == "ARCH":
                    print("[ARCH_TRACE][supervisor.step] output status:", output.get("status") if isinstance(output, dict) else None)
                    print("[ARCH_TRACE][supervisor.step] output keys:", list(output.keys()) if isinstance(output, dict) else None)
                    print("[ARCH_TRACE][supervisor.step] output errors:", output.get("errors") if isinstance(output, dict) else None)
                    print("[ARCH_TRACE][supervisor.step] output warnings:", output.get("warnings") if isinstance(output, dict) else None)

                evaluation = evaluate_step(
                    agent_name,
                    output,
                    step.get("required_output_keys", []),
                )
                if debug and str(state.get("docs_cd", "")).upper() == "ARCH":
                    print("[ARCH_TRACE][supervisor.eval] agent:", agent_name)
                    print("[ARCH_TRACE][supervisor.eval] required:", step.get("required_output_keys", []))
                    print("[ARCH_TRACE][supervisor.eval] success:", evaluation.get("success"))
                    print("[ARCH_TRACE][supervisor.eval] failure_type:", evaluation.get("failure_type"))
                    print("[ARCH_TRACE][supervisor.eval] action:", evaluation.get("action"))
                    print("[ARCH_TRACE][supervisor.eval] message:", evaluation.get("message"))
                    print("[ARCH_TRACE][supervisor.eval] failed_checks:", evaluation.get("failed_checks"))

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
        state.setdefault("max_round", 2)
        state.setdefault("warnings", [])
        state.setdefault("errors", [])
        state.setdefault("current_repair_instruction", None)
        state.setdefault("repair_history", [])
        state.setdefault("repair_round", 0)
        state.setdefault("max_repair_round", state.get("max_round", 2))
        state["status"] = "RUNNING"
        state["next_action"] = "CONTINUE"

    @staticmethod
    def _prepare_repair(state: WorkflowState, failure: dict[str, Any]) -> None:
        next_round = int(state.get("repair_round", 0)) + 1
        if next_round > int(state.get("max_repair_round", state.get("max_round", 2))):
            state["current_repair_instruction"] = None
            return
        instruction = build_repair_instruction(failure, repair_round=next_round)
        state["current_repair_instruction"] = instruction
        if instruction is None:
            return
        state["repair_round"] = next_round
        state["repair_history"].append(
            {
                "repair_id": instruction["repair_id"],
                "status": "PENDING",
                "instruction": instruction,
            }
        )

    @staticmethod
    def _finish_repair(state: WorkflowState, status: str) -> None:
        instruction = state.get("current_repair_instruction")
        if not instruction:
            return
        repair_id = instruction.get("repair_id")
        for entry in reversed(state.get("repair_history", [])):
            if entry.get("repair_id") == repair_id and entry.get("status") == "PENDING":
                entry["status"] = status
                entry["validation_result"] = state.get("validation_result")
                break
        state["current_repair_instruction"] = None

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
