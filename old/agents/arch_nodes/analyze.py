import json

from agents.arch_nodes.common import extract_json
from services.llm_client import call_llm
from workflows.architecture_state import ArchitectureWorkflowState


ANALYZER_SYSTEM_PROMPT = """
너는 금융 시스템 요구사항 분석 전문가이다.
주어진 요구사항 리스트를 분석하여 시스템 인프라 설계에 영향을 미칠 만한 비기능적 요소, 기술적 제약사항, 필요 미들웨어 기능을 추론 및 추출하라.
각 요구사항 항목별로 분석 결과를 생성하라.

반드시 다른 부연 설명 없이 아래 지정된 JSON 리스트 포맷으로만 답변해야 한다.
[
  {
    "requirement_id": "ID 복사",
    "requirement_name": "명칭 복사",
    "non_functional_elements": ["성능/보안/가용성 측면의 필요 요소 추출"],
    "technical_constraints": ["인프라 레벨의 제약사항 정리"],
    "implied_middleware_needs": ["필요 메커니즘 예: Kafka, WebSocket, Redis, RDBMS-HA 등"]
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
                    "non_functional_elements": ["파싱 오류로 인한 수동 검토 필요"],
                    "technical_constraints": [f"데이터 포맷 에러 방어: {exc}"],
                    "implied_middleware_needs": ["기본 WAS/DB 레이어 적용"],
                }
            ],
            "validation_errors": [f"요구사항 분석 실패: {exc}"],
        }
