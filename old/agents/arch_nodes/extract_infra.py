import json

from agents.arch_nodes.common import extract_json
from services.llm_client import call_llm
from workflows.architecture_state import ArchitectureWorkflowState


EXTRACTOR_SYSTEM_PROMPT = """
너는 20년 차 금융 시스템 인프라 아키텍트이다.
분석가 에이전트들이 취합한 비기능 요구사항 리스트와 사용자의 인프라 제약 사양을 바탕으로, 온프레미스 환경에 최적화된 시스템 아키텍처 구성 요소들을 도출하고 각 구성 요소간 흐름을 설계하라.

반드시 다른 설명 없이 오직 다음 구조의 JSON 포맷으로만 출력하라.
{
  "system_architecture": ["시스템 아키텍처 구성 요소들"],
  "selected_middleware": ["확정 미들웨어 스택"],
  "security_architecture": "요구사항에 필요한 방화벽 및 세션/보안 인증 방식 요약"
}
""".strip()


def extract_infra_node(state: ArchitectureWorkflowState) -> ArchitectureWorkflowState:
    payload = {
        "analyzed_reqs": state.get("analyzed_reqs", []),
        "user_infra_spec": state.get("user_infra_spec", {}),
    }

    try:
        content = call_llm(
            EXTRACTOR_SYSTEM_PROMPT,
            json.dumps(payload, ensure_ascii=False),
            temperature=0.1,
        )
        extracted_infra = extract_json(content)
        return {"extracted_infra": extracted_infra}
    except Exception as exc:
        return {
            "extracted_infra": {
                "network_zones": {
                    "DMZ": ["Web Server"],
                    "Internal_Zone": ["Core API WAS"],
                    "DB_Zone": ["Primary DB"],
                },
                "selected_middleware": state.get("user_infra_spec", {}).get("middleware_stack", ["Standard Stack"]),
                "security_architecture": "기본 온프레미스 보안 표준 적용",
            },
            "validation_errors": [f"인프라 구성 추출 실패: {exc}"],
        }
