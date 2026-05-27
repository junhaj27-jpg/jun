import json

from services.llm_client import call_llm
from workflows.architecture_state import ArchitectureWorkflowState


SPEC_GENERATOR_PROMPT = """
당신은 엔터프라이즈 인프라 아키텍처 명세서 작성 전문가입니다.
분석된 요구사항과 도출된 인프라 구성안을 매핑하여 아키텍처 설계서 본문을 마크다운으로 작성하세요.

포함 항목:
- 아키텍처 개요
- 요구사항별 구현 방안 표
- 미들웨어 구성
- 보안/네트워크 구성
- 운영 고려사항
""".strip()


def generate_spec_node(state: ArchitectureWorkflowState) -> ArchitectureWorkflowState:
    payload = {
        "analyzed_reqs": state.get("analyzed_reqs", []),
        "extracted_infra": state.get("extracted_infra", {}),
    }

    try:
        report_specs = call_llm(
            SPEC_GENERATOR_PROMPT,
            json.dumps(payload, ensure_ascii=False),
            temperature=0,
        ).strip()
    except Exception as exc:
        report_specs = f"# 아키텍처 설계서\n\n명세 생성 실패: {exc}\n"

    return {"report_specs": report_specs}

