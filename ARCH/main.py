import json
from graph.workflow import compile_agent_graph
from graph.state import RequirementDocument

def run_agent_pipeline():
    # 1. 에이전트 그래프 엔진 컴파일
    app = compile_agent_graph()
    
    # 2. 테스트용 사용자의 인프라 사양 컨텍스트 정의
    user_infra_spec = {
        "middleware_stack": "Apache, Tomcat, Oracle, Redis",
        "firewall_setting": "DMZ-내부망 간 2차 방화벽 구성 및 특정 포트 차단",
        "security_auth": "한국은행 세션 검증 전용 인증 모듈 연동",
        "expected_ccu": 5000,
        "is_cloud": False, # 온프레미스 단독 구동 환경
        "server_hardware_spec": "Web/WAS: 16vCPU, 64GB / DB: 32vCPU, 128GB NVMe SSD Raid-10"
    }
    
    # 3. 사용자가 제공한 JSON 요구사항 문서 바인딩
    raw_json_input = {
        "requirements": [
            {
            "requirement_id": "SSR-F01001",
            "requirement_name": "온프레미스 생성형 AI 실행환경 제공",
            "requirement_type": "기능",
            "description": "시스템은 외부 인터넷 연결 없이 내부망 환경에서 운영 가능한 온프레미스 기반 생성형 AI 실행환경을 제공해야 하며, 멀티 LLM, 임베딩 모델, 벡터 DB 및 GPU 기반 추론 환경을 통합 구성해야 한다.",
            "source": [
                "RFP(SFR-001 생성형 AI 기본사항)"
            ],
            "constraints": [
                "외부 인터넷 연결 없이 내부망에서 운영 가능해야 함",
                "10G 내부망 환경에서 동작 가능해야 함",
                "온프레미스 방식으로 구축되어야 함"
            ],
            "priority": "상",
            "validation_criteria": [
                "외부 인터넷 연결 없이 질의응답 서비스가 정상 수행되는가?",
                "LLM, 임베딩 모델, 벡터DB가 통합된 환경에서 정상 동작하는가?",
                "GPU 기반 추론 처리 성능이 정상적으로 제공되는가?"
            ],
            "note": "전체 플랫폼의 기반 인프라 요구사항"
            },
            {
            "requirement_id": "SSR-F01002",
            "requirement_name": "멀티 LLM 실행 환경 제공",
            "requirement_type": "기능",
            "description": "시스템은 다양한 생성형 AI 모델을 업무 목적에 따라 선택하여 사용할 수 있는 멀티 LLM 실행 환경을 제공해야 하며, 서비스 특성별 최적 모델을 운영자가 관리할 수 있어야 한다.",
            "source": [
                "RFP(SFR-001)",
                "RFP(SFR-002 AI 적용 모델)"
            ],
            "constraints": [
                "구축 시점 최신 파운데이션 모델 지원",
                "복수 모델 동시 운영 가능"
            ],
            "priority": "상",
            "validation_criteria": [
                "운영자가 복수의 LLM 모델을 등록·선택할 수 있는가?",
                "업무별 모델 선택 후 정상 응답이 가능한가?"
            ],
            "note": "문서작성·코딩·번역 등 목적별 최적화 모델 필요"
            },
            {
            "requirement_id": "SSR-F01003",
            "requirement_name": "멀티턴 대화 및 문맥 유지",
            "requirement_type": "기능",
            "description": "시스템은 사용자의 이전 질문과 응답 문맥을 기억하고 후속 질의에 반영할 수 있는 멀티턴 대화 기능을 제공해야 한다.",
            "source": [
                "RFP(SFR-001 생성형 AI 기본사항)"
            ],
            "constraints": [
                "세션 단위 문맥 유지"
            ],
            "priority": "상",
            "validation_criteria": [
                "이전 질문 맥락을 반영한 후속 응답이 가능한가?",
                "세션 변경 시 대화 이력이 분리 관리되는가?"
            ],
            "note": "AI 포털 챗봇형 UI와 연계"
            },
            {
            "requirement_id": "SSR-F01004",
            "requirement_name": "다중 문서 업로드 기반 질의응답",
            "requirement_type": "기능",
            "description": "사용자는 복수 문서를 업로드하여 해당 자료 기반 질의응답을 수행할 수 있어야 하며, 시스템은 문서 내용을 기반으로 응답을 생성해야 한다.",
            "source": [
                "RFP(SFR-001)",
                "RFP(SFR-011 생성형 AI 포털 구축)"
            ],
            "constraints": [
                "최소 3개 이상 문서 동시 업로드 지원",
                "HWP, PDF, DOCX, XLSX, PPTX, CSV 형식 지원",
                "DRM 문서 복호화 지원"
            ],
            "priority": "상",
            "validation_criteria": [
                "3개 이상 문서 업로드 후 질의응답이 가능한가?",
                "문서 기반 응답 시 출처가 표시되는가?"
            ],
            "note": "문서 기반 질의응답 핵심 기능"
            },
            {
            "requirement_id": "SSR-F01005",
            "requirement_name": "RAG 기반 의미 검색 및 응답",
            "requirement_type": "기능",
            "description": "시스템은 벡터 임베딩 기반 의미 검색과 Advanced RAG 기법을 활용하여 내부 문서 및 데이터에 대한 정확한 질의응답 기능을 제공해야 한다.",
            "source": [
                "RFP(SFR-004 검색증강생성 RAGOps)"
            ],
            "constraints": [
                "벡터DB 기반 검색",
                "Hybrid Search 및 문서 재정렬 지원",
                "DRM 문서 복호화 지원"
            ],
            "priority": "상",
            "validation_criteria": [
                "의미 기반 검색 결과가 제공되는가?",
                "응답 시 출처 문서가 표시되는가?",
                "질의 재구성 및 재정렬이 정상 동작하는가?"
            ],
            "note": "할루시네이션 최소화 목적"
            },
            {
            "requirement_id": "SSR-I02001",
            "requirement_name": "SSO 및 ERP 계정 연계",
            "requirement_type": "인터페이스",
            "description": "시스템은 기관 ERP 및 SSO 환경과 연계하여 사용자 계정 자동 생성, 조직정보 동기화 및 자동 로그인을 지원해야 한다.",
            "source": [
                "RFP(SIR-002)",
                "RFP(SFR-011)"
            ],
            "constraints": [
                "조직정보 자동 동기화",
                "자동 로그인 지원"
            ],
            "priority": "상",
            "validation_criteria": [
                "ERP 사용자 생성 시 계정이 자동 생성되는가?",
                "SSO 로그인 후 별도 인증 없이 접근 가능한가?"
            ],
            "note": "권한관리 연계 필수"
            }
        ]
    }
    
    # Pydantic 스키마 무결성 1차 검증 및 할당
    req_doc = RequirementDocument(**raw_json_input)
    
    # 4. 에이전트 구동 데이터 세팅 및 호출
    initial_state = {
        "requirements_doc": req_doc,
        "user_infra_spec": user_infra_spec,
        "analyzed_reqs": [],
        "retry_count": 0
    }
    
    print("=== 온프레미스 아키텍처 설계 멀티 에이전트 시스템 가동 ===")
    final_state = app.invoke(initial_state)
    
    print("\n=== 최종 산출 보고서 ===")
    print(final_state.get("mermaid_script"))

if __name__ == "__main__":
    run_agent_pipeline()


## 새로 만든 파일 image_node / mermaid_node/spec_node 에서 llm 호출하는 코드를 
## 기존 있던 파일 analyzer_node/extractor_node 에 맞춰서 만들기 
## 아니면 이 공통 부분 util 로 통합해서 만들어도 되고
## invoke 할 때 llm 에 호출하지 말고 chain 만들어서 chain.invoke 하도록 수정.
## prompt 도 같이 template 으로 수정해서 같이 넣기