# nodes/pass1.py
import logging
import os

from agents.srs_state import State
from agents.srs_llm_service import LLMService
from agents.srs_prompts import GENERATION_SYSTEM, build_pass1_prompt

logger = logging.getLogger(__name__)
llm = LLMService()
_CHUNK_SIZE = 10

def pass1_node(state: State) -> dict:
    draft_reqs = []
    rfp = state["rfp"]
    use_llm = os.getenv("SRS_PASS1_USE_LLM", "false").strip().lower() in {"1", "true", "yes", "y"}

    if not use_llm:
        logger.info("pass1: SRS_PASS1_USE_LLM=false, RFP 원문 기반으로 즉시 생성합니다.")
        return {"draft_reqs": _fallback_requirements(rfp)}

    for idx in range(0, len(rfp), _CHUNK_SIZE):
        chunk = rfp[idx:idx + _CHUNK_SIZE]
        result = llm.complete_json(
            GENERATION_SYSTEM,
            build_pass1_prompt(chunk, state["cleaned_minutes"], state["rag_context"]),
        )
        if result.get("_parse_error"):
            logger.warning("pass1: chunk %d failed", idx // _CHUNK_SIZE + 1)
            draft_reqs.extend(_fallback_requirements(chunk))
            continue

        draft_reqs.extend(result.get("requirements", []))

    return {"draft_reqs": draft_reqs}


def _fallback_requirements(rfp_items: list[dict]) -> list[dict]:
    requirements = []
    for item in rfp_items:
        if not isinstance(item, dict):
            continue

        original_id = item.get("requirement_id") or item.get("id") or ""
        source = item.get("source") or []
        if isinstance(source, str):
            source = [source]
        source = [*source]
        if original_id:
            source.append(original_id)

        requirements.append(
            {
                "requirement_id": "",
                "requirement_name": item.get("requirement_name") or item.get("name") or "요구사항",
                "requirement_type": item.get("requirement_type") or "기능",
                "description": item.get("description") or item.get("content") or "",
                "source": source or ["RFP"],
                "constraints": item.get("constraints") or [],
                "priority": item.get("priority") or "중",
                "validation_criteria": item.get("validation_criteria") or ["RFP 원문 반영 여부를 확인한다."],
                "note": "LLM 응답 실패로 RFP 원문 기반으로 생성됨",
            }
        )
    return requirements
