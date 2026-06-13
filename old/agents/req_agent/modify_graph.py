from langgraph.graph import StateGraph, END
from state import ModifyState
from nodes.rag_modify    import rag_modify_node
from nodes.modify        import modify_node
from nodes.safety_modify import safety_modify_node
from nodes.merge_modify  import merge_modify_node

def build_modify_graph():
    g = StateGraph(ModifyState)

    g.add_node("rag",    rag_modify_node)
    g.add_node("modify", modify_node)
    g.add_node("safety", safety_modify_node)
    g.add_node("merge",  merge_modify_node)

    g.set_entry_point("rag")
    g.add_edge("rag",    "modify")
    g.add_edge("modify", "safety")
    g.add_edge("safety", "merge")
    g.add_edge("merge",  END)

    return g.compile()