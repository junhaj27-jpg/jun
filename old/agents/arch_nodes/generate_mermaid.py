import json

from services.llm_client import call_llm
from workflows.architecture_state import ArchitectureWorkflowState
from agents.arch_nodes.common import wrap_mermaid_block


MERMAID_GENERATOR_PROMPT = """
당신은 시스템 인프라 아키텍처를 시각화하는 Mermaid 다이어그램 설계 전문가입니다.
제공된 인프라 구성안을 기반으로, 온프레미스 서버 구조와 네트워크 흐름을 보여주는 상세한 Mermaid 아키텍처 코드를 작성하세요.
subgraph를 적극 활용하여 영역을 격리하세요.

[출력 가이드라인]
1. 다른 설명이나 인사말은 일체 제외하고 오직 ```mermaid 로 시작해서 ```로 끝나는 코드 블록만 출력하세요.
2. 노드 ID는 반드시 영문 대문자/숫자/언더스코어만 사용하세요. 예: K8S_CLUSTER[K8s Cluster]
3. 노드 ID에는 공백, 하이픈, 한글을 절대 쓰지 말고, 표시명은 대괄호 안에만 작성하세요.
4. 화살표 방향 및 노드 ID 문법 규칙을 철저히 지키세요.
""".strip()


def generate_mermaid_node(state: ArchitectureWorkflowState) -> ArchitectureWorkflowState:
    try:
        mermaid_script = call_llm(
            MERMAID_GENERATOR_PROMPT,
            json.dumps(state.get("extracted_infra", {}), ensure_ascii=False),
            temperature=0.1,
        ).strip()
    except Exception as exc:
        mermaid_script = f"""```mermaid
flowchart TD
    USER[User] --> WEB[Web Server]
    WEB --> WAS[Application Server]
    WAS --> DB[(Database)]
```"""

    return {"mermaid_script": wrap_mermaid_block(mermaid_script)}
