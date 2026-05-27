# 수정 파이프라인용 safety (modified_reqs 검증)
import logging
from agents.srs_state import ModifyState
from agents.srs_core.validator import is_grounded
from rag.srs_rag_service import RAGService
from agents.srs_pipeline_config import PIPELINE

logger = logging.getLogger(__name__)
rag    = RAGService()

def safety_modify_node(state: ModifyState) -> dict:
    validated = []
    for req in state["modified_reqs"]:
        r = is_grounded(req, state["instruction"], rag,
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
