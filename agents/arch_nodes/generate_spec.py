import json

from services.llm_client import call_llm
from workflows.architecture_state import ArchitectureWorkflowState


SPEC_GENERATOR_PROMPT = """
당신은 엔터프라이즈 인프라 아키텍처 명세서 작성 전문가입니다.
제공된 '분석된 요구사항'과 '도출된 인프라 구성안'을 철저히 매핑하여, 요구사항별 기술 명세 섹션을 마크다운 표(Table)와 상세 텍스트 형식으로 작성하세요.
명세 섹션은 각 요구사항별로 '요구사항 ID, 요구사항 내용, 구현 방안'을 포함해야 합니다.
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
        report_specs = ""

    return {"report_specs": report_specs}
