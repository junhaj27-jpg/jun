# 문서 코드에 맞는 Validator를 선택하여 산출물을 검증합니다.

from typing import Any

from agents.validation.schemas import build_validation_result, make_check
from agents.validation.validators import VALIDATORS
from workflow.state import WorkflowState


class ValidationAgent:
    def execute(self, state: WorkflowState) -> dict[str, Any]:
        docs_cd = str(state.get("docs_cd", "")).upper()
        validator = VALIDATORS.get(docs_cd)
        if validator is None:
            checks = [
                make_check(
                    "VALIDATION_DOCS_CD_001",
                    "산출물 코드 검증",
                    False,
                    failure_type="INVALID_DOCS_CD",
                    message=f"지원하지 않는 docs_cd입니다: {docs_cd}",
                    target_agent="validation_agent",
                )
            ]
        else:
            checks = validator(state)
        validation_result = build_validation_result(docs_cd, checks)
        output = {
            "status": validation_result["validation_status"],
            "validation_result": validation_result,
            "warnings": [
                check for check in checks if check["status"] == "WARN"
            ],
            "errors": [],
        }
        state.setdefault("agent_outputs", {})["validation_agent"] = output
        return output
