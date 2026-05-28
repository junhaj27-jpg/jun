from agents.srs_state import State


def analyze_node(state: State) -> dict:
    topics = []
    for item in state["rfp"]:
        if not isinstance(item, dict):
            continue
        for key in ("requirement_name", "requirement_type"):
            value = str(item.get(key, "")).strip()
            if value and value not in topics:
                topics.append(value)
        if len(topics) >= 20:
            break

    return {"topics": topics}
