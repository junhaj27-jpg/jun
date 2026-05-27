# nodes/pass1.py
from state import State
from services.llm_service import LLMService
from prompts import GENERATION_SYSTEM, build_pass1_prompt

llm = LLMService()

def pass1_node(state: State) -> dict:
    result = llm.complete_json(
        GENERATION_SYSTEM,
        build_pass1_prompt(state["rfp"], state["cleaned_minutes"], state["rag_context"]),
    )
    return {"draft_reqs": result.get("requirements", [])}