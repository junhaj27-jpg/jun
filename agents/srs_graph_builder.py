from langgraph.graph import StateGraph, END
from agents.srs_state import State
from agents.srs_nodes.normalize import normalize_node
from agents.srs_nodes.analyze import analyze_node
from agents.srs_nodes.rag import rag_node
from agents.srs_nodes.pass1 import pass1_node
from agents.srs_nodes.merge import merge_node


def skip_review_node(state: State) -> dict:
    return {"refined_reqs": state.get("draft_reqs", [])}


def skip_safety_node(state: State) -> dict:
    validated = []
    for req in state.get("refined_reqs", []):
        item = req.copy()
        item["_grounded"] = True
        item["_score"] = 1.0
        item["_reason"] = "safety skipped for fast generation"
        validated.append(item)
    return {"validated_reqs": validated}


def build_graph():
    g = StateGraph(State)

    g.add_node("normalize", normalize_node)
    g.add_node("analyze",   analyze_node)
    g.add_node("rag",       rag_node)
    g.add_node("pass1",     pass1_node)
    g.add_node("skip_review", skip_review_node)
    g.add_node("skip_safety", skip_safety_node)
    g.add_node("merge",     merge_node)

    g.set_entry_point("normalize")
    g.add_edge("normalize", "analyze")
    g.add_edge("analyze",   "rag")
    g.add_edge("rag",       "pass1")
    g.add_edge("pass1",     "skip_review")
    g.add_edge("skip_review", "skip_safety")
    g.add_edge("skip_safety", "merge")
    g.add_edge("merge",     END)

    return g.compile()
