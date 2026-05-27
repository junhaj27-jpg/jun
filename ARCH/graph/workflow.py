from langgraph.graph import StateGraph, END, START
from graph.state import AgentState

# 각 노드 임포트
from nodes.analyzer_node import analyzer_node
from nodes.extractor_node import extractor_node
from nodes.spec_generator_node import spec_generator_node       # 신설
from nodes.mermaid_generator_node import mermaid_generator_node # 신설
from nodes.validator_node import validator_node
from nodes.image_generator_node import image_generator_node     # 신설

MAX_RETRIES = 3

def conditional_validation_route(state: AgentState):
    """
    validator_node 통과 여부 및 리트라이 한계치에 따른 조건부 라우팅 함수
    """
    val_res = state.get("validation_result", {})
    
    # 1. 문법 검증 통과 시 -> 이미지 렌더링 및 최종 조립 노드로 전진
    if val_res.get("status") == "PASS":
        print("\n[Route] 🎉 Mermaid 문법 검증 통과! 이미지 빌드 단계로 진입합니다.")
        return "image_generator_node"
    
    # 2. 문법 실패 시 리트라이 카운트 체크
    current_retry = state.get("retry_count", 0)
    if current_retry >= MAX_RETRIES:
        print(f"\n[Route] 🛑 최대 시도 횟수({MAX_RETRIES}회) 초과로 루프를 강제 종료합니다.")
        return END
        
    # 3. 한계치 미만일 경우 -> '텍스트 노드'를 건너뛰고 'Mermaid 전용 노드'로만 리턴 (최적화 핵심)
    print(f"\n[Route] 🔄 문법 오류 발견. Mermaid 전용 재생성 노드로 복귀합니다. (현재 누적 재시도: {current_retry + 1}/{MAX_RETRIES})")
    return "mermaid_generator_node"

def compile_agent_graph():
    # 1. 그래프 인스턴스 초기화
    workflow = StateGraph(AgentState)
    
    # 2. 신규 파이프라인 컴포넌트(노드) 일괄 등록
    workflow.add_node("analyzer_node", analyzer_node)
    workflow.add_node("extractor_node", extractor_node)
    workflow.add_node("spec_generator_node", spec_generator_node)
    workflow.add_node("mermaid_generator_node", mermaid_generator_node)
    workflow.add_node("validator_node", validator_node)
    workflow.add_node("image_generator_node", image_generator_node)
    
    # 3. 단방향 고정 흐름 선언
    workflow.add_edge(START, "analyzer_node")
    workflow.add_edge("analyzer_node", "extractor_node")
    workflow.add_edge("extractor_node", "spec_generator_node")       # 텍스트 명세 작성 (1회성)
    workflow.add_edge("spec_generator_node", "mermaid_generator_node") # Mermaid 작성 (루프 진입점)
    workflow.add_edge("mermaid_generator_node", "validator_node")     # 문법 검증 실행
    
    # 4. 검증 결과에 따른 조건부 분기 구조 바인딩
    workflow.add_conditional_edges(
        "validator_node",
        conditional_validation_route,
        {
            "image_generator_node": "image_generator_node", # 성공 시 타는 길
            "mermaid_generator_node": "mermaid_generator_node", # 실패 시 좁은 격리 루프로 복귀하는 길
            END: END # 한계치 도달 시 멈추는 길
        }
    )
    
    # 5. 최종 산출 및 파일 저장이 끝나면 프로세스 완결
    workflow.add_edge("image_generator_node", END)
    
    return workflow.compile()