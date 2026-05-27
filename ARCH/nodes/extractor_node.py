import json
import re
from langchain_community.chat_models import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from config import MODEL_NAME, OLLAMA_BASE_URL
from graph.state import AgentState

EXTRACTOR_SYSTEM_PROMPT = """
너는 20년 차 금융 시스템 인프라 아키텍트이다.
분석가 에이전트들이 취합한 비기능 요구사항 리스트와 사용자의 인프라 제약 사양을 바탕으로, 온프레미스 환경에 최적화된 시스템 아키텍처 구성 요소들을 도출하고 각 구성 요소간 흐름을 설계하라.

반드시 다른 설명 없이 오직 다음 구조의 JSON 포맷으로만 출력하라.
{{
    "system_architecture": ["시스템 아키텍처 구성 요소들"],
    "selected_middleware": ["인프라 요구사항을 해결하기 위한 확정 미들웨어 스택"],
    "security_architecture": "요구사항에 필요한 방화벽 및 세션/보안 인증 방식 요약"
}}
"""

def extractor_node(state: AgentState):
    analyzed_reqs = state["analyzed_reqs"]
    user_infra_spec = state["user_infra_spec"]
    
    llm = ChatOllama(model=MODEL_NAME, base_url=OLLAMA_BASE_URL, temperature=0.1)
    prompt = ChatPromptTemplate.from_messages([
        ("system", EXTRACTOR_SYSTEM_PROMPT),
        ("human", "취합된 요구사항 분석 데이터:\n{reqs}\n\n사용자 지정 인프라 제약사양:\n{spec}")
    ])
    
    chain = prompt | llm
    
    try:
        response = chain.invoke({
            "reqs": json.dumps(analyzed_reqs, ensure_ascii=False),
            "spec": json.dumps(user_infra_spec, ensure_ascii=False)
        })
        content = response.content.strip()
        
        # 정규표현식을 사용한 JSON 추출
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            content = json_match.group()
            
        extracted_infra = json.loads(content)
    except Exception as e:
        # 인프라 추출 레이어 폴백 데이터
        print(f"extractor_node exception block >>>>>>>>>> Error: {e}")
        extracted_infra = {
            "network_zones": {"DMZ": ["Web Server"], "Internal_Zone": ["Core API WAS"], "DB_Zone": ["Primary DB"]},
            "selected_middleware": user_infra_spec.get("middleware_stack", ["Standard Stack"]),
            "security_architecture": "기본 온프레미스 보안 표준 적용"
        }
        
    return {"extracted_infra": extracted_infra}