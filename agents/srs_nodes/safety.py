# nodes/safety.py
import logging
from agents.srs_state import State
from agents.srs_core.validator import is_grounded
from rag.srs_rag_service import RAGService
from agents.srs_pipeline_config import PIPELINE

logger = logging.getLogger(__name__)
rag    = RAGService()

def safety_node(state: State) -> dict:
    validated = []
    for req in state["refined_reqs"]:
        r = is_grounded(req, state["cleaned_minutes"], rag,
                        lex_threshold=PIPELINE["lex_threshold"],
                        rag_threshold=PIPELINE["rag_threshold"],
                        min_matches=PIPELINE["min_matches"])
        req["_grounded"] = r.is_grounded
        req["_score"]    = r.score
        req["_reason"]   = r.reason
        if not r.is_grounded:
            logger.warning("safety: ungrounded %s — %s",
                           req.get("requirement_id", "?"), r.reason)
        validated.append(req)
    return {"validated_reqs": validated}
