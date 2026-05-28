# nodes/pass1.py
import logging

from agents.srs_state import State
from agents.srs_llm_service import LLMService
from agents.srs_prompts import GENERATION_SYSTEM, build_pass1_prompt

logger = logging.getLogger(__name__)
llm = LLMService()

def pass1_node(state: State) -> dict:
    draft_reqs = []
    for idx, rfp_req in enumerate(state["rfp"], start=1):
        result = llm.complete_json(
            GENERATION_SYSTEM,
            build_pass1_prompt([rfp_req], state["cleaned_minutes"], state["rag_context"]),
        )
        requirements = result.get("requirements", [])
        if result.get("_parse_error"):
            logger.warning("pass1: RFP %d JSON parse failed", idx)
            continue
        if not requirements:
            logger.info("pass1: RFP %d generated no requirements", idx)
            continue

        rfp_id = str(rfp_req.get("requirement_id", "")).strip()
        for req in requirements:
            _append_source(req, rfp_id)
            draft_reqs.append(req)

    return {"draft_reqs": draft_reqs}


def _append_source(req: dict, rfp_id: str) -> None:
    if not rfp_id:
        return
    source = req.get("source")
    if isinstance(source, list):
        if rfp_id not in source:
            source.append(rfp_id)
    elif source:
        req["source"] = [source, rfp_id] if source != rfp_id else [rfp_id]
    else:
        req["source"] = [rfp_id]
