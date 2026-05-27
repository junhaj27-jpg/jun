from graph.state import AgentState

def validator_node(state: AgentState):
    script = state.get("mermaid_script", "")
    retry_count = state.get("retry_count", 0)
    errors = []
    
    if "```mermaid" not in script:
        errors.append("Mermaid 코드 블록 정의(```mermaid)를 찾을 수 없습니다.")
        
    # 기본 제약 구문 매칭 검증 (subgraph와 end의 쌍 개수 체크)
    subgraph_count = script.count("subgraph")
    end_count = script.count("end")
    if subgraph_count != end_count:
        errors.append(f"전체 구조의 subgraph 개수({subgraph_count})와 문을 닫는 end 개수({end_count})가 일치하지 않습니다.")
        
    if errors:
        return {
            "validation_result": {"status": "FAIL", "errors": errors},
            "retry_count": retry_count + 1
        }
    
    return {"validation_result": {"status": "PASS", "errors": []}}