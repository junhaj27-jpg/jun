# 수정 파이프라인용 merge
# 기존 요구사항에서 변경/삭제/추가 반영
from agents.srs_state import ModifyState
from agents.srs_core.id_manager import assign_ids
from agents.srs_pipeline_config import PIPELINE

_OUTPUT_KEYS = [
    "requirement_id", "requirement_name", "requirement_type",
    "description", "source", "constraints",
    "priority", "validation_criteria", "note", "status",
]
_INTERNAL = {"_grounded", "_score", "_reason"}

def merge_modify_node(state: ModifyState) -> dict:
    existing   = state["existing_reqs"]
    modified   = state["validated_reqs"]

    existing_map = {r.get("requirement_id", "").strip(): r for r in existing}
    kept_existing = []
    new_items = []

    for req in modified:
        item = req.copy()
        rid = item.get("requirement_id", "").strip()
        if rid and rid in existing_map:
            item["status"] = "기존" if _same_requirement(existing_map[rid], item) else "수정"
            kept_existing.append(item)
        else:
            item["status"] = "신규"
            new_items.append(item)

    # LLM 응답에 없는 기존 요구사항은 삭제된 것으로 처리한다.
    assigned = assign_ids(existing, new_items, prefix=PIPELINE["req_prefix"])
    all_reqs = kept_existing + assigned

    final_reqs  = [_to_output(r) for r in all_reqs]
    review_reqs = [_to_review(r) for r in all_reqs if not r.get("_grounded", True)]

    return {
        "final_reqs":  final_reqs,
        "review_reqs": review_reqs,
    }

def _to_output(req):
    return {k: req.get(k) for k in _OUTPUT_KEYS}

def _to_review(req):
    base = _to_output(req)
    base.update({k: req.get(k) for k in _INTERNAL})
    return base

def _same_requirement(left: dict, right: dict) -> bool:
    for key in _OUTPUT_KEYS:
        if key == "status":
            continue
        if left.get(key) != right.get(key):
            return False
    return True
