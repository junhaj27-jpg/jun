from agents.srs_state import State
from agents.srs_llm_service import LLMService
from agents.srs_prompts import REFINE_SYSTEM, build_pass2_prompt
from agents.srs_nodes.chunking import chunk_items, compact_item, compact_text

llm = LLMService()

def pass2_node(state: State) -> dict:
    refined_reqs = []
    cleaned_minutes = compact_text(state["cleaned_minutes"])
    rag_context = compact_text(state["rag_context"])
    rfp_lookup = _build_rfp_lookup(state["rfp"])

    for chunk_index, draft_chunk in enumerate(chunk_items(state["draft_reqs"]), start=1):
        related_rfp = _select_related_rfp(draft_chunk, rfp_lookup)
        print(f"[SRS pass2] chunk {chunk_index}: {len(draft_chunk)} requirements", flush=True)
        result = llm.complete_json(
            REFINE_SYSTEM,
            build_pass2_prompt(
                related_rfp,
                cleaned_minutes,
                rag_context,
                draft_chunk,
            ),
        )
        refined_reqs.extend(result.get("requirements", []) or draft_chunk)

    return {"refined_reqs": refined_reqs}


def _build_rfp_lookup(rfp: list[dict]) -> dict[str, dict]:
    lookup = {}
    for item in rfp:
        if not isinstance(item, dict):
            continue
        compacted = compact_item(item)
        for key in ("requirement_id", "requirement_name"):
            value = str(item.get(key, "")).strip()
            if value:
                lookup[value] = compacted
    return lookup


def _select_related_rfp(draft_chunk: list[dict], rfp_lookup: dict[str, dict]) -> list[dict]:
    related = []
    seen = set()
    for req in draft_chunk:
        candidates = [
            str(req.get("requirement_id", "")).strip(),
            str(req.get("requirement_name", "")).strip(),
        ]
        source = req.get("source", [])
        if isinstance(source, str):
            candidates.append(source)
        elif isinstance(source, list):
            candidates.extend(str(item).strip() for item in source)

        for candidate in candidates:
            if candidate in rfp_lookup and candidate not in seen:
                related.append(rfp_lookup[candidate])
                seen.add(candidate)

    if related:
        return related
    return list(rfp_lookup.values())[: min(5, len(rfp_lookup))]
