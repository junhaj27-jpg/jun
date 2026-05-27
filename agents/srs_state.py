from typing import TypedDict, NotRequired

class State(TypedDict):
    rfp:              list[dict]
    minutes:          str
    existing_reqs:    NotRequired[list[dict]]
    cleaned_minutes:  str
    topics:           list[str]
    rag_context:      str
    draft_reqs:       list[dict]
    refined_reqs:     list[dict]
    validated_reqs:   list[dict]
    final_reqs:       list[dict]
    review_reqs:      list[dict]


class ModifyState(TypedDict):
    existing_reqs:    list[dict]   # 현재 저장된 REQ-xxx
    instruction:      str          # 수정 프롬프트 or 새 회의록
    rag_context:      str
    modified_reqs:    list[dict]
    validated_reqs:   list[dict]
    final_reqs:       list[dict]
    review_reqs:      list[dict]