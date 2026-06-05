import logging
from state import ModifyState
from core.id_manager import assign_ids
from pipeline_config import PIPELINE

logger = logging.getLogger(__name__)

_OUTPUT_KEYS = [
    "requirement_id", "requirement_name", "requirement_type",
    "description", "source", "constraints",
    "priority", "validation_criteria", "note", "status",
]
_INTERNAL = {"_grounded", "_score", "_reason"}

def merge_modify_node(state: ModifyState) -> dict:
    existing     = state["existing_reqs"]
    modified     = state["validated_reqs"]
    returned_ids = {r.get("requirement_id", "").strip() for r in modified}

    survivors = []
    for r in existing:
        rid = r["requirement_id"]
        if rid in returned_ids:
            mod = next((m for m in modified if m.get("requirement_id") == rid), None)
            if mod:
                mod["status"] = "수정"
                survivors.append(mod)
            else:
                survivors.append({**r, "status": r.get("status", "기존")})

    new_items = [r for r in modified if not r.get("requirement_id", "").strip()]
    for r in new_items:
        r["status"] = "신규"

    assigned    = assign_ids(survivors, new_items, prefix=PIPELINE["req_prefix"])
    final_reqs  = [_to_output(r) for r in survivors + assigned]
    review_reqs = [_to_review(r) for r in survivors + assigned
                   if not r.get("_grounded", True)]
    return {"final_reqs": final_reqs, "review_reqs": review_reqs}

def _to_output(req): return {k: req.get(k) for k in _OUTPUT_KEYS}
def _to_review(req):
    base = _to_output(req)
    base.update({k: req.get(k) for k in _INTERNAL})
    return base
