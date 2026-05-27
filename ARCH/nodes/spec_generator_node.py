import json
from graph.state import AgentState
from langchain_community.chat_models import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from config import MODEL_NAME, OLLAMA_BASE_URL  


SPEC_GENERATOR_PROMPT = """
당신은 엔터프라이즈 인프라 아키텍처 명세서 작성 전문가입니다.
제공된 '분석된 요구사항'과 '도출된 인프라 구성안'을 철저히 매핑하여, 요구사항별 기술 명세 섹션을 마크다운 표(Table)와 상세 텍스트 형식으로 작성하세요.
명세 섹션은 각 요구사항별로 '요구사항 ID, 요구사항 내용, 구현 방안'을 포함해야 합니다.

"""
def spec_generator_node(state: AgentState):
    extracted_infra = state.get("extracted_infra", {})
    analyzed_reqs = state.get("analyzed_reqs", [])

    llm = ChatOllama(model=MODEL_NAME, base_url=OLLAMA_BASE_URL, temperature=0)
    prompt = ChatPromptTemplate.from_messages([
        ("system", SPEC_GENERATOR_PROMPT),
        ("human", "분석된 요구사항:\n{analyzed_reqs}\n\n도출된 인프라 구성안:\n{extracted_infra}")
    ])

    chain = prompt | llm


    try:
        response = chain.invoke({
            "analyzed_reqs": json.dumps(analyzed_reqs, ensure_ascii=False),
            "extracted_infra": json.dumps(extracted_infra, ensure_ascii=False)
        })

        report_specs = response.content.strip()
    except Exception as e:
        # 인프라 추출 레이어 폴백 데이터
        print(f"spec_generator_node exception block >>>>>>>>>> Error: {e}")
        report_specs = ""

    return {"report_specs": report_specs}