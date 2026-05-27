import json

from agents.arch_nodes.common import extract_json
from services.llm_client import call_llm
from workflows.architecture_state import ArchitectureWorkflowState


EXTRACTOR_SYSTEM_PROMPT = """
너는 20년 차 엔터프라이즈 인프라 아키텍트이다.
분석된 요구사항과 사용자의 인프라 제약 사양을 바탕으로 시스템 아키텍처 구성 요소, 미들웨어, 보안 구조를 도출하라.

반드시 아래 JSON 객체만 출력하라.
{
  "system_architecture": ["구성 요소"],
  "network_zones": {"zone_name": ["component"]},
  "selected_middleware": ["확정 미들웨어 스택"],
  "security_architecture": "보안/방화벽/인증 구조 요약",
  "deployment_considerations": ["배포/운영 고려사항"]
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
                    "Internal": ["Application Server"],
                    "Data": ["Database"],
                },
                "selected_middleware": ["Web", "WAS", "RDBMS"],
                "security_architecture": "기본 온프레미스 보안 표준 적용",
                "deployment_considerations": [f"추출 실패로 기본 구조 사용: {exc}"],
            },
            "validation_errors": [f"인프라 구성 추출 실패: {exc}"],
        }

