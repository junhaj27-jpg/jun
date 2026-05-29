from agents.srs_state import State
from agents.srs_llm_service import LLMService
from agents.srs_prompts import ANALYZE_SYSTEM, build_analyze_prompt
from agents.srs_nodes.chunking import chunk_items, compact_text

llm = LLMService()

def analyze_node(state: State) -> dict:
    topics = []
    cleaned_minutes = compact_text(state["cleaned_minutes"])

    for chunk_index, rfp_chunk in enumerate(chunk_items(state["rfp"]), start=1):
        print(f"[SRS analyze] chunk {chunk_index}: {len(rfp_chunk)} requirements", flush=True)
        result = llm.complete_json(
            ANALYZE_SYSTEM,
            build_analyze_prompt(rfp_chunk, cleaned_minutes),
        )
        for topic in result.get("topics", []):
            if topic and topic not in topics:
                topics.append(topic)

    return {"topics": topics}
