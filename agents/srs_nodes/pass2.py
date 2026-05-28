# nodes/pass2.py
import logging

from agents.srs_state import State
from agents.srs_llm_service import LLMService
from agents.srs_prompts import REFINE_SYSTEM, build_pass2_prompt

logger = logging.getLogger(__name__)
llm = LLMService()
_CHUNK_SIZE = 10

def pass2_node(state: State) -> dict:
    refined_reqs = []
    draft_reqs = state["draft_reqs"]

    for idx in range(0, len(draft_reqs), _CHUNK_SIZE):
        chunk = draft_reqs[idx:idx + _CHUNK_SIZE]
        result = llm.complete_json(
            REFINE_SYSTEM,
            build_pass2_prompt(
                state["rfp"], state["cleaned_minutes"],
                state["rag_context"], chunk,
            ),
        )
        if result.get("_parse_error"):
            logger.warning("pass2: chunk %d failed, keeping original draft", idx // _CHUNK_SIZE + 1)
            refined_reqs.extend(chunk)
            continue

        refined_reqs.extend(result.get("requirements", []) or chunk)

    return {"refined_reqs": refined_reqs}
