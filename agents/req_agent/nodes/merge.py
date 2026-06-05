import logging
from state import State
from core.id_manager import assign_ids
from pipeline_config import PIPELINE

logger = logging.getLogger(__name__)

_OUTPUT_KEYS = [
    "requirement_id", "requirement_name", "requirement_type",
    "description", "source", "constraints",
    "priority", "validation_criteria", "note", "status",
]
_INTERNAL = {"_grounded", "_score", "_reason"}

def merge_node(state: State) -> dict:
    existing = state.get("existing_reqs", [])
    new_reqs = state["validated_reqs"]

    for r in new_reqs:
        r.setdefault("source", ["generated"])
        r["status"] = "신규"

    assigned    = assign_ids(existing, new_reqs, prefix=PIPELINE["req_prefix"])
    final_reqs  = [_to_output(r) for r in assigned]
    review_reqs = [_to_review(r) for r in assigned if not r.get("_grounded", True)]

    existing_tagged = [{**r, "status": r.get("status", "기존")} for r in existing]
    return {"final_reqs": existing_tagged + final_reqs, "review_reqs": review_reqs}

def _to_output(req): return {k: req.get(k) for k in _OUTPUT_KEYS}
def _to_review(req):
    base = _to_output(req)
    base.update({k: req.get(k) for k in _INTERNAL})
    return base
