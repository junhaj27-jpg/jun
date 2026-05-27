# nodes/analyze.py
from agents.srs_state import State
from agents.srs_llm_service import LLMService
from agents.srs_prompts import ANALYZE_SYSTEM, build_analyze_prompt

llm = LLMService()

def analyze_node(state: State) -> dict:
    result = llm.complete_json(
        ANALYZE_SYSTEM,
        build_analyze_prompt(state["rfp"], state["cleaned_minutes"]),
    )
    return {"topics": result.get("topics", [])}
