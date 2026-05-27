from langgraph.graph import StateGraph, END
from state import State
from nodes.normalize import normalize_node
from nodes.analyze   import analyze_node
from nodes.rag       import rag_node
from nodes.pass1     import pass1_node
from nodes.pass2     import pass2_node
from nodes.safety    import safety_node
from nodes.merge     import merge_node

def build_graph():
    g = StateGraph(State)

    g.add_node("normalize", normalize_node)
    g.add_node("analyze",   analyze_node)
    g.add_node("rag",       rag_node)
    g.add_node("pass1",     pass1_node)
    g.add_node("pass2",     pass2_node)
    g.add_node("safety",    safety_node)
    g.add_node("merge",     merge_node)

    g.set_entry_point("normalize")
    g.add_edge("normalize", "analyze")
    g.add_edge("analyze",   "rag")
    g.add_edge("rag",       "pass1")
    g.add_edge("pass1",     "pass2")
    g.add_edge("pass2",     "safety")
    g.add_edge("safety",    "merge")
    g.add_edge("merge",     END)

    return g.compile()