# nodes/normalize.py
from state import State
from utils.text_cleaner import clean_minutes

def normalize_node(state: State) -> dict:
    return {"cleaned_minutes": clean_minutes(state["minutes"])}