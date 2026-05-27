# nodes/pass2.py
from state import State
from services.llm_service import LLMService
from prompts import REFINE_SYSTEM, build_pass2_prompt

llm = LLMService()

def pass2_node(state: State) -> dict:
    result = llm.complete_json(
        REFINE_SYSTEM,
        build_pass2_prompt(
            state["rfp"], state["cleaned_minutes"],
            state["rag_context"], state["draft_reqs"],
        ),
    )
    return {"refined_reqs": result.get("requirements", [])}