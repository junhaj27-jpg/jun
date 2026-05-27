import json

from agents.arch_nodes.common import extract_json
from services.llm_client import call_llm
from workflows.architecture_state import ArchitectureWorkflowState


ANALYZER_SYSTEM_PROMPT = """
너는 금융/SI 시스템 요구사항 분석 전문가이다.
주어진 요구사항 리스트를 분석하여 시스템 인프라 설계에 영향을 미칠 비기능 요소, 기술 제약사항, 필요 미들웨어 기능을 추론하라.

반드시 아래 JSON 리스트만 출력하라.
[
  {
    "requirement_id": "ID",
    "requirement_name": "요구사항명",
    "non_functional_elements": ["성능/보안/가용성 요소"],
    "technical_constraints": ["인프라 레벨 제약사항"],
    "implied_middleware_needs": ["필요 미들웨어 또는 메커니즘"]
  }
]
""".strip()


def analyze_requirements_node(state: ArchitectureWorkflowState) -> ArchitectureWorkflowState:
    requirement_doc = state["requirement_doc"]
    requirements = requirement_doc.get("requirements", [])

    try:
        content = call_llm(
            ANALYZER_SYSTEM_PROMPT,
            json.dumps(requirements, ensure_ascii=False),
            temperature=0,
        )
        parsed = extract_json(content)
        if isinstance(parsed, dict):
            parsed = [parsed]
        return {"analyzed_reqs": parsed}
    except Exception as exc:
        return {
            "analyzed_reqs": [
                {
                    "requirement_id": "UNKNOWN",
                    "requirement_name": "UNKNOWN",
                    "non_functional_elements": ["수동 검토 필요"],
                    "technical_constraints": [f"분석 실패: {exc}"],
                    "implied_middleware_needs": ["기본 Web/WAS/DB 레이어"],
                }
            ],
            "validation_errors": [f"요구사항 분석 실패: {exc}"],
        }

