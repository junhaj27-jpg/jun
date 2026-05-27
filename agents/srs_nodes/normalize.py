# nodes/normalize.py
from agents.srs_state import State
from agents.srs_utils.text_cleaner import clean_minutes

def normalize_node(state: State) -> dict:
    return {"cleaned_minutes": clean_minutes(state["minutes"])}
