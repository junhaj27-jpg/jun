import json
from graph.state import AgentState
from langchain_community.chat_models import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from config import MODEL_NAME, OLLAMA_BASE_URL  

MERMAID_GENERATOR_PROMPT = """

당신은 시스템 인프라 아키텍처를 시각화하는 Mermaid 다이어그램 설계 전문가입니다.
제공된 인프라 구성안을 기반으로, 온프레미스 서버 구조와 네트워크 흐름을 보여주는 상세한 Mermaid 아키텍처 코드를 작성하세요.
subgraph를 적극 활용하여 영역을 격리하세요.

[출력 가이드라인]
1. 다른 설명이나 인사말은 일체 제외하고 오직 ```mermaid 로 시작해서 ```로 끝나는 코드 블록만 출력하세요.
2. 화살표 방향 및 노드 ID 문법 규칙을 철저히 지키세요.
"""


def mermaid_generator_node(state: AgentState):

    extracted_infra = state.get("extracted_infra", {})
    val_res = state.get("validation_result", {})
    current_retry = state.get("retry_count", 0)
    
    # 검증 실패 후 리트라이 루프를 돌 때만 피드백 삽입
    error_feedback = ""
    next_retry_count = current_retry
    if val_res and val_res.get("status") == "FAIL":
        next_retry_count += 1
        error_feedback = (
            f"\n\n⚠️ [이전 생성 결과 문법 오류 발생 - 반드시 수정할 것]\n"
            f"발생한 에러 내용: {val_res.get('errors', 'Mermaid Syntax Error')}\n"
            f"지적된 라인/원인을 파악하여 올바른 상위-하위 격리 구조(subgraph)를 가진 Mermaid 코드로 수정하세요."
        )
    ## error_feedback 붙이려다 만 것
    

    llm = ChatOllama(model=MODEL_NAME, base_url=OLLAMA_BASE_URL, temperature=0.1)
    prompt = ChatPromptTemplate.from_messages([
        ("system", MERMAID_GENERATOR_PROMPT),
        ("human", "대상 인프라 구성안:\n{extracted_infra}")
    ])
    
    chain = prompt | llm


    try:
        response = chain.invoke({
            "extracted_infra": json.dumps(extracted_infra, ensure_ascii=False),
        })

        mermaid_script = response.content.strip()
    except Exception as e:
        # 인프라 추출 레이어 폴백 데이터
        print(f"mermaid_generator_node exception block >>>>>>>>>> Error: {e}")
        mermaid_script = ""

    return {
        "mermaid_script": mermaid_script,
        "retry_count": next_retry_count
    }