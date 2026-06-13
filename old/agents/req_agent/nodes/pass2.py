import logging
from state import State
from services.llm_service import LLMService
from prompts import REFINE_SYSTEM, build_pass2_prompt
from nodes.chunking import chunk_items

logger = logging.getLogger(__name__)
llm    = LLMService()
_CHUNK = 5

def pass2_node(state: State) -> dict:
    draft = state["draft_reqs"]
    if not draft:
        return {"refined_reqs": []}

    refined = []
    for i in range(0, len(draft), _CHUNK):
        chunk = draft[i:i + _CHUNK]
        logger.info("pass2: %d~%d / %d", i+1, min(i+_CHUNK, len(draft)), len(draft))
        result = llm.complete_json(
            REFINE_SYSTEM,
            build_pass2_prompt(state["rfp"], state["cleaned_minutes"],
                               state["rag_context"], chunk),
        )
        reqs = result.get("requirements", [])
        if not reqs:
            logger.warning("pass2: 청크 %d 빈 응답 -> 원본 유지", i)
            reqs = chunk
        refined.extend(reqs)

    logger.info("pass2: 총 %d개", len(refined))
    return {"refined_reqs": refined}
