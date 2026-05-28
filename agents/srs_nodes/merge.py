# nodes/merge.py
from agents.srs_state import State
from agents.srs_core.id_manager import assign_ids
from agents.srs_pipeline_config import PIPELINE

_INTERNAL_KEYS = {"_grounded", "_score", "_reason", "_parse_error", "_llm_error", "_raw"}

_OUTPUT_KEYS = [
    "requirement_id", "requirement_name", "requirement_type",
    "description", "source", "constraints",
    "priority", "validation_criteria", "note", "status",
]

def merge_node(state: State) -> dict:
    existing = state.get("existing_reqs", [])
    new_reqs = state["validated_reqs"]

    for r in new_reqs:
        r.setdefault("source", ["generated"])
        r["status"] = "신규"

    assigned = assign_ids(existing, new_reqs, prefix=PIPELINE["req_prefix"])
    existing_reqs = [_mark_existing(r) for r in existing]

    # 출력용 / 검토용 분리
    final_reqs   = [_to_output(r) for r in assigned]
    review_reqs  = [_to_review(r) for r in assigned if not r.get("_grounded", True)]

    return {
        "final_reqs":  existing_reqs + final_reqs,
        "review_reqs": review_reqs,   # ungrounded만 따로
    }

def _mark_existing(req: dict) -> dict:
    item = req.copy()
    item["status"] = item.get("status") or "기존"
    return _to_output(item)

def _to_output(req: dict) -> dict:
    """입력과 동일한 포맷으로 정제"""
    return {k: req.get(k) for k in _OUTPUT_KEYS}

def _to_review(req: dict) -> dict:
    """검토자용 — 출력 포맷 + 플래그"""
    base = _to_output(req)
    base["_grounded"] = req.get("_grounded", True)
    base["_score"]    = req.get("_score", 0.0)
    base["_reason"]   = req.get("_reason", "")
    return base
