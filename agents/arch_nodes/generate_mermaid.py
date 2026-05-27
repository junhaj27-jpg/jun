import json

from services.llm_client import call_llm
from workflows.architecture_state import ArchitectureWorkflowState


MERMAID_GENERATOR_PROMPT = """
당신은 시스템 인프라 아키텍처를 시각화하는 Mermaid 다이어그램 설계 전문가입니다.
제공된 인프라 구성안을 기반으로 온프레미스/클라우드 여부, 네트워크 존, 서버, DB, 보안 흐름을 보여주는 Mermaid flowchart를 작성하세요.

규칙:
1. 오직 ```mermaid 코드 블록만 출력하세요.
2. flowchart LR 또는 flowchart TD를 사용하세요.
3. subgraph를 사용하되 subgraph와 end 개수를 반드시 맞추세요.
4. 노드 ID에는 공백과 특수문자를 쓰지 마세요.
""".strip()


def generate_mermaid_node(state: ArchitectureWorkflowState) -> ArchitectureWorkflowState:
    validation_result = state.get("validation_result", {})
    retry_count = state.get("retry_count", 0)
    error_feedback = ""

    if validation_result.get("status") == "FAIL":
        error_feedback = (
            "\n\n이전 Mermaid 검증 오류를 수정하세요:\n"
            + json.dumps(validation_result.get("errors", []), ensure_ascii=False)
        )
        retry_count += 1

    try:
        mermaid_script = call_llm(
            MERMAID_GENERATOR_PROMPT,
            json.dumps(state.get("extracted_infra", {}), ensure_ascii=False) + error_feedback,
            temperature=0.1,
        ).strip()
    except Exception as exc:
        mermaid_script = f"""```mermaid
flowchart TD
    USER[User] --> WEB[Web Server]
    WEB --> WAS[Application Server]
    WAS --> DB[(Database)]
    ERR[Mermaid generation failed: {str(exc).replace('"', "'")}]
```"""

    return {"mermaid_script": mermaid_script, "retry_count": retry_count}

