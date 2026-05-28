# nodes/pass1.py
import logging

from agents.srs_state import State
from agents.srs_llm_service import LLMService
from agents.srs_prompts import GENERATION_SYSTEM, build_pass1_prompt

logger = logging.getLogger(__name__)
llm = LLMService()
_CHUNK_SIZE = 20

def pass1_node(state: State) -> dict:
    draft_reqs = []
    rfp = state["rfp"]

    for idx in range(0, len(rfp), _CHUNK_SIZE):
        chunk = rfp[idx:idx + _CHUNK_SIZE]
        result = llm.complete_json(
            GENERATION_SYSTEM,
            build_pass1_prompt(chunk, state["cleaned_minutes"], state["rag_context"]),
        )
        if result.get("_parse_error"):
            logger.warning("pass1: chunk %d failed", idx // _CHUNK_SIZE + 1)
            continue

        draft_reqs.extend(result.get("requirements", []))

    return {"draft_reqs": draft_reqs}
