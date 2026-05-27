# nodes/analyze.py
from state import State
from services.llm_service import LLMService
from prompts import ANALYZE_SYSTEM, build_analyze_prompt

llm = LLMService()

def analyze_node(state: State) -> dict:
    result = llm.complete_json(
        ANALYZE_SYSTEM,
        build_analyze_prompt(state["rfp"], state["cleaned_minutes"]),
    )
    return {"topics": result.get("topics", [])}