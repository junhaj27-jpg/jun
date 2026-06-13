# LangGraph 워크플로우 노드의 연결과 실행 흐름을 정의합니다.

from langgraph.graph import END, START, StateGraph

from workflow.nodes.cleanup_node import cleanup_node
from workflow.nodes.export_node import export_node
from workflow.nodes.generation_supervisor_node import generation_supervisor_node
from workflow.nodes.request_preprocess_node import request_preprocess_node
from workflow.state import WorkflowState


def route_after_preprocess(state: WorkflowState) -> str:
    return "cleanup_node" if state.get("status") == "FAILED" else "generation_supervisor_node"


def build_workflow():
    graph = StateGraph(WorkflowState)

    graph.add_node("request_preprocess_node", request_preprocess_node)
    graph.add_node("generation_supervisor_node", generation_supervisor_node)
    graph.add_node("export_node", export_node)
    graph.add_node("cleanup_node", cleanup_node)

    graph.add_edge(START, "request_preprocess_node")
    graph.add_conditional_edges(
        "request_preprocess_node",
        route_after_preprocess,
        {
            "generation_supervisor_node": "generation_supervisor_node",
            "cleanup_node": "cleanup_node",
        },
    )
    graph.add_edge("generation_supervisor_node", "export_node")
    graph.add_edge("export_node", "cleanup_node")
    graph.add_edge("cleanup_node", END)

    return graph.compile()


workflow = build_workflow()
