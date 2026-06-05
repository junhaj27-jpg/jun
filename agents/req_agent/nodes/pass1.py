import logging
from state import State
from services.llm_service import LLMService
from prompts import GENERATION_SYSTEM, build_pass1_prompt
from nodes.chunking import chunk_items, compact_text

logger = logging.getLogger(__name__)
llm    = LLMService()

def pass1_node(state: State) -> dict:
    all_reqs        = []
    cleaned_minutes = compact_text(state["cleaned_minutes"])
    rag_context     = compact_text(state["rag_context"])

    for i, rfp_chunk in enumerate(chunk_items(state["rfp"]), start=1):
        rfp_ids = [r.get("requirement_id","") for r in rfp_chunk]
        logger.info("pass1: 청크 %d (%s)", i, ", ".join(rfp_ids))

        result = llm.complete_json(
            GENERATION_SYSTEM,
            build_pass1_prompt(rfp_chunk, cleaned_minutes, rag_context),
        )
        reqs = result.get("requirements", [])
        if not reqs:
            logger.warning("pass1: 청크 %d 빈 응답", i)

        for req in reqs:
            src = req.get("source", [])
            for rfp_id in rfp_ids:
                if rfp_id and rfp_id not in src:
                    src.append(rfp_id)
            req["source"] = src

        all_reqs.extend(reqs)

    logger.info("pass1: 총 %d개 생성", len(all_reqs))
    return {"draft_reqs": all_reqs}
