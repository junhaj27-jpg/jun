# LangGraph 워크플로우 노드의 연결과 실행 흐름을 정의합니다.

from langgraph.graph import END, START, StateGraph

from services.generation_job_progress import update_generation_job_progress
from workflow.nodes.cleanup_node import cleanup_node
from workflow.nodes.export_node import export_node
from workflow.nodes.generation_supervisor_node import generation_supervisor_node
from workflow.nodes.request_preprocess_node import request_preprocess_node
from workflow.state import WorkflowState


def _run_preprocess(state: WorkflowState) -> WorkflowState:
    update_generation_job_progress(
        state,
        step="PREPROCESSING",
        progress=10,
        message="요청 정보와 입력 파일을 확인하고 있습니다.",
    )
    return request_preprocess_node(state)


def _run_supervisor(state: WorkflowState) -> WorkflowState:
    update_generation_job_progress(
        state,
        step="GENERATING",
        progress=30,
        message="AI 산출물을 생성하고 검증하고 있습니다.",
    )
    return generation_supervisor_node(state)


def _run_export(state: WorkflowState) -> WorkflowState:
    update_generation_job_progress(
        state,
        step="EXPORTING",
        progress=90,
        message="생성 결과를 문서로 저장하고 있습니다.",
    )
    return export_node(state)


def _run_cleanup(state: WorkflowState) -> WorkflowState:
    update_generation_job_progress(
        state,
        step="CLEANUP",
        progress=95,
        message="임시 리소스를 정리하고 있습니다.",
    )
    return cleanup_node(state)


def route_after_preprocess(state: WorkflowState) -> str:
    return "cleanup_node" if state.get("status") == "FAILED" else "generation_supervisor_node"


def route_after_supervisor(state: WorkflowState) -> str:
    return "cleanup_node" if state.get("status") == "FAILED" else "export_node"


def build_workflow():
    graph = StateGraph(WorkflowState)

    graph.add_node("request_preprocess_node", _run_preprocess)
    graph.add_node("generation_supervisor_node", _run_supervisor)
    graph.add_node("export_node", _run_export)
    graph.add_node("cleanup_node", _run_cleanup)

    graph.add_edge(START, "request_preprocess_node")
    graph.add_conditional_edges(
        "request_preprocess_node",
        route_after_preprocess,
        {
            "generation_supervisor_node": "generation_supervisor_node",
            "cleanup_node": "cleanup_node",
        },
    )
    graph.add_conditional_edges(
        "generation_supervisor_node",
        route_after_supervisor,
        {
            "export_node": "export_node",
            "cleanup_node": "cleanup_node",
        },
    )
    graph.add_edge("export_node", "cleanup_node")
    graph.add_edge("cleanup_node", END)

    return graph.compile()


workflow = build_workflow()
