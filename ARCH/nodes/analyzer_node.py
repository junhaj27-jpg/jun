import json
import re
from langchain_community.chat_models import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from config import MODEL_NAME, OLLAMA_BASE_URL
from graph.state import AgentState

ANALYZER_SYSTEM_PROMPT = """
너는 금융 시스템 요구사항 분석 전문가이다.
주어진 요구사항 리스트를 분석하여 시스템 인프라 설계에 영향을 미칠 만한 비기능적 요소, 기술적 제약사항, 필요 미들웨어 기능을 추론 및 추출하라.
각 요구사항 항목별로 분석 결과를 생성하라.

반드시 다른 부연 설명 없이 아래 지정된 JSON 리스트 포맷으로만 답변해야 한다.
[
    {{
        "requirement_id": "ID 복사",
        "requirement_name": "명칭 복사",
        "non_functional_elements": ["성능/보안/가용성 측면의 필요 요소 추출"],
        "technical_constraints": ["인프라 레벨의 제약사항 정리"],
        "implied_middleware_needs": ["필요 메커니즘 예: Kafka, WebSocket, Redis, RDBMS-HA 등"]
    }}
]
"""

def analyzer_node(state: AgentState):
    req_doc = state["requirements_doc"]
    # Pydantic 모델인 경우 dict로 변환, 리스트 추출
    requirements = req_doc.requirements if hasattr(req_doc, 'requirements') else req_doc.get('requirements', [])
    
    llm = ChatOllama(model=MODEL_NAME, base_url=OLLAMA_BASE_URL, temperature=0)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", ANALYZER_SYSTEM_PROMPT),
        ("human", "분석할 요구사항 리스트:\n{req_data}")
    ])
    
    chain = prompt | llm
    req_data_str = json.dumps([r.dict() if hasattr(r, 'dict') else r for r in requirements], ensure_ascii=False)
    
    # [개선안 1] 소형 LLM 전용 구조화 출력 에러 방어 루프
    for attempt in range(2):
        try:
            response = chain.invoke({"req_data": req_data_str})
            content = response.content.strip()
            
            # 정규표현식을 사용한 JSON 추출 (더욱 견고한 파싱)
            json_match = re.search(r'(\[.*\]|\{.*\})', content, re.DOTALL)
            if json_match:
                content = json_match.group(1)
                
            parsed_json = json.loads(content)
            
            # 결과가 단일 객체인 경우 리스트로 감싸줌 (리듀서 대응)
            if isinstance(parsed_json, dict):
                parsed_json = [parsed_json]
                
            return {"analyzed_reqs": parsed_json}
            
        except (json.JSONDecodeError, Exception) as e:
            print(f"analyzer_node exception block >>>>>>>>>> Error: {e}")
            if attempt == 1:
                # 2회 시도 모두 실패 시 시스템 다운을 막기 위한 폴백 구조체 반환
                return {"analyzed_reqs": [{
                    "requirement_id": "UNKNOWN",
                    "requirement_name": "UNKNOWN",
                    "non_functional_elements": ["파싱 오류로 인한 수동 검토 필요"],
                    "technical_constraints": [f"데이터 포맷 에러 방어: {str(e)}"],
                    "implied_middleware_needs": ["기본 WAS/DB 레이어 적용"]
                }]}
    return {"analyzed_reqs": []}