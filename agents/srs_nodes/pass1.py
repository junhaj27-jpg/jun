from agents.srs_state import State
from agents.srs_llm_service import LLMService
from agents.srs_prompts import GENERATION_SYSTEM, build_pass1_prompt
from agents.srs_nodes.chunking import chunk_items, compact_text

llm = LLMService()

def pass1_node(state: State) -> dict:
    draft_reqs = []
    cleaned_minutes = compact_text(state["cleaned_minutes"])
    rag_context = compact_text(state["rag_context"])

    for chunk_index, rfp_chunk in enumerate(chunk_items(state["rfp"]), start=1):
        print(f"[SRS pass1] chunk {chunk_index}: {len(rfp_chunk)} requirements", flush=True)
        result = llm.complete_json(
            GENERATION_SYSTEM,
            build_pass1_prompt(rfp_chunk, cleaned_minutes, rag_context),
        )
        draft_reqs.extend(result.get("requirements", []))

    return {"draft_reqs": draft_reqs}
