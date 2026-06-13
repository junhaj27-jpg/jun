import json
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from agents.erd_agent import REQ_JSON_PATH
from agents.ts_agent import generate_test_scenarios
from generators.ts_docx_generator import generate_ts_docx
from workflows.ts_state import TestScenarioWorkflowState


def load_ts_inputs_node(state: TestScenarioWorkflowState) -> TestScenarioWorkflowState:
    requirement_json_path = state.get("requirement_json_path") or REQ_JSON_PATH
    with open(requirement_json_path, encoding="utf-8") as file:
        requirement_doc = json.load(file)

    ui_screens_raw = []
    for ui_path in state.get("ui_paths", []):
        path = Path(ui_path)
        if path.exists():
            ui_screens_raw.append(path.read_text(encoding="utf-8"))

    return {
        "requirement_json_path": requirement_json_path,
        "requirement_doc": requirement_doc,
        "ui_screens_raw": ui_screens_raw,
    }


def generate_ts_node(state: TestScenarioWorkflowState) -> TestScenarioWorkflowState:
    test_scenario_doc = generate_test_scenarios(
        state.get("requirement_doc", {}),
        state.get("ui_screens_raw") or None,
        max_retries=state.get("max_retries", 0),
    )
    scenarios = test_scenario_doc.get("scenarios", [])
    cases = test_scenario_doc.get("cases", [])
    errors = test_scenario_doc.get("errors", [])
    if not scenarios or not cases:
        return {
            "test_scenario_doc": test_scenario_doc,
            "summary": test_scenario_doc.get("summary", {}),
            "status": "INVALID",
            "validation_errors": errors or [{"error": "생성된 scenarios/cases가 없습니다."}],
        }
    return {
        "test_scenario_doc": test_scenario_doc,
        "summary": test_scenario_doc.get("summary", {}),
        "status": "VALID",
    }


def save_ts_json_node(state: TestScenarioWorkflowState) -> TestScenarioWorkflowState:
    output_json_path = state.get("output_json_path") or "./json_temp/ts_agent_output.json"
    payload = state.get("test_scenario_doc", {})
    Path(output_json_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_json_path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"output_json_path": output_json_path}


def generate_ts_docx_node(state: TestScenarioWorkflowState) -> TestScenarioWorkflowState:
    if state.get("status") != "VALID":
        return {"status": "INVALID"}

    output_docx_path = state.get("output_docx_path") or "./output/통합 시험 시나리오.docx"
    generate_ts_docx(state.get("test_scenario_doc", {}), output_docx_path)
    return {"output_docx_path": output_docx_path, "status": "VALID"}


def compile_ts_graph():
    workflow = StateGraph(TestScenarioWorkflowState)

    workflow.add_node("load_ts_inputs_node", load_ts_inputs_node)
    workflow.add_node("generate_ts_node", generate_ts_node)
    workflow.add_node("save_ts_json_node", save_ts_json_node)
    workflow.add_node("generate_ts_docx_node", generate_ts_docx_node)

    workflow.add_edge(START, "load_ts_inputs_node")
    workflow.add_edge("load_ts_inputs_node", "generate_ts_node")
    workflow.add_edge("generate_ts_node", "save_ts_json_node")
    workflow.add_edge("save_ts_json_node", "generate_ts_docx_node")
    workflow.add_edge("generate_ts_docx_node", END)

    return workflow.compile()
