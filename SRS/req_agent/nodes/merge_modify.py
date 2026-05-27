# 수정 파이프라인용 merge
# 기존 요구사항에서 변경/삭제/추가 반영
from state import ModifyState
from core.id_manager import assign_ids
from pipeline_config import PIPELINE

_OUTPUT_KEYS = [
    "requirement_id", "requirement_name", "requirement_type",
    "description", "source", "constraints",
    "priority", "validation_criteria", "note",
]
_INTERNAL = {"_grounded", "_score", "_reason"}

def merge_modify_node(state: ModifyState) -> dict:
    existing   = state["existing_reqs"]
    modified   = state["validated_reqs"]

    # LLM이 반환한 ID 기준으로 기존 항목 교체/추가
    existing_map = {r["requirement_id"]: r for r in existing}

    for req in modified:
        rid = req.get("requirement_id", "").strip()
        if rid and rid in existing_map:
            existing_map[rid] = req          # 기존 항목 교체
        else:
            existing_map[f"__new__{id(req)}"] = req  # 신규 항목

    # LLM 응답에 없는 기존 항목 = 삭제된 것 → 유지 (삭제는 명시적으로만)
    # → LLM이 반환한 ID 목록에 없으면 삭제로 처리
    returned_ids = {r.get("requirement_id", "").strip() for r in modified}
    survivors    = [r for r in existing if r["requirement_id"] in returned_ids]
    new_items    = [r for r in modified if not r.get("requirement_id", "").strip()
                    or r.get("requirement_id") not in {e["requirement_id"] for e in existing}]

    # 신규 항목 ID 발급
    assigned = assign_ids(survivors, new_items, prefix=PIPELINE["req_prefix"])
    all_reqs = survivors + assigned

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