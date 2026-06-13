# 여러 Agent의 출력을 최종 결과로 취합합니다.

from supervisor.reduce.reduce_harness import get_empty_document_json
from workflow.state import WorkflowState


def reduce_outputs(state: WorkflowState) -> WorkflowState:
    state["final_document_json"] = get_empty_document_json(state["docs_cd"])
    state["next_action"] = "EXPORT"
    return state
