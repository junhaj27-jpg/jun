from agents.srs_state import ModifyState
from agents.srs_llm_service import LLMService
from agents.srs_prompts import MODIFY_SYSTEM, build_modify_prompt

llm = LLMService()

def modify_node(state: ModifyState) -> dict:
    result = llm.complete_json(
        MODIFY_SYSTEM,
        build_modify_prompt(
            state["existing_reqs"],
            state["instruction"],
            state["rag_context"],
        ),
    )
    return {"modified_reqs": result.get("requirements", [])}
