"""
[PHASE 1] 공통 설정 및 인프라 유틸리티 (v2 - 다중 컬렉션 지원)

변경 사항 (v1 → v2):
  - Qdrant 컬렉션을 2개로 분리
      rfp_knowledge_base     : RFP + 기술/보안 표준 가이드 (Agent 1 Mode B, Agent 2)
      requirements_knowledge_base : 과거 요구사항 명세서 JSON (Agent 1 Mode A)
  - doc_type 메타데이터 체계 추가
      scope   : 현재 프로젝트 RFP (최우선 기준)
      rule    : 보안/기술 규정, 법령 (절대 위배 금지)
      pattern : 유사 사업 RFP (참고용)
      generated_req : 과거 생성된 요구사항 명세서 (패턴 학습용)

[로컬 환경 체크리스트]
  1. Ollama 설치: https://ollama.com
  2. 모델 다운로드: ollama pull solar (또는 원하는 모델)
  3. 패키지 설치:
       pip install qdrant-client sentence-transformers requests fastapi uvicorn pydantic
       pip install pymupdf python-docx  # 문서 읽기용
       pip install libretranslatepy==2.1.1
  4. Ollama 서버 확인: http://localhost:11434
"""

import json
import requests
import atexit
from typing import List

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

# ─────────────────────────────────────────────
# 설정값
# ─────────────────────────────────────────────
CONFIG = {
    # sLLM 설정
    "sllm_url":   "http://localhost:11434/api/chat",
    "sllm_model": "qwen2.5:3b",   # ollama list 로 확인 후 변경
    "temperature": 0.5,

    # 임베딩 모델 (한국어 지원, 768차원)
    "embedding_model": "jhgan/ko-sroberta-multitask",
    "vector_dim": 768,

    # Qdrant 로컬 파일 DB 경로
    "qdrant_path": "./qdrant_db",

    # ─ 컬렉션 이름 ────────────────────────────
    # Agent 1 Mode B + Agent 2 검증용 (RFP, 가이드, 법령)
    "rfp_collection": "rfp_knowledge_base",
    # Agent 1 Mode A용 (과거 요구사항 명세서 패턴)
    "req_collection": "requirements_knowledge_base",

    # RAG 검색 결과 개수
    "top_k": 3,
}

# ─────────────────────────────────────────────
# doc_type 분류 (메타데이터 태깅 기준)
# ─────────────────────────────────────────────
DOC_TYPE = {
    "scope":         "현재 프로젝트 RFP – 무조건 준수",
    "rule":          "보안/기술 법령 가이드 – 절대 위배 금지",
    "pattern":       "유사 사업 RFP – 아이디어 참고, 상충 시 무시",
    "generated_req": "과거 생성 요구사항 명세서 – 패턴 학습용",
}

# ─────────────────────────────────────────────
# sLLM 프롬프트 주입용 JSON 출력 형식 가이드
# ─────────────────────────────────────────────
JSON_FORMAT_GUIDE = """\
반드시 아래 JSON 구조로만 응답하라.
설명문, 인사말, 마크다운 코드블록(```) 절대 금지. 오직 JSON만 출력.

{
  "requirements": [
    {
      "requirement_id": "REQ-001",
      "requirement_name": "요구사항명 (간결하게)",
      "requirement_type": "기능",
      "description": "구체적이고 측정 가능한 상세 설명. 로직과 동작 방식 포함.",
      "source": ["출처문서명"],
      "constraints": ["제약사항1", "제약사항2"],
      "priority": "상",
      "validation_criteria": ["테스트 방법 또는 완료 기준"],
      "note": null
    }
  ]
}

허용값:
  requirement_type → "기능" 또는 "비기능"
  priority        → "상" 또는 "중" 또는 "하"
  note            → 문자열 또는 null
"""

# ─────────────────────────────────────────────
# sLLM Agent 1 Mode A 시스템 프롬프트 (회의록 기반)
# ─────────────────────────────────────────────
AGENT1_MINUTES_SYSTEM = """\
당신은 15년 경력의 요구사항 엔지니어링(RE) 전문가입니다.
[역할]
회의록을 분석하여 요구사항 명세서를 생성하는 '창조자(Creator)'.

[핵심 규칙 (RAG 우선순위)]
1. [현재 회의록]의 내용은 요구사항의 "핵심 요건"으로 무조건 반영한다.
2. [RAG 패턴/가이드] 데이터는 요구사항의 "구체성, 상세 설명, 검증 기준"을 보완하기 위한 필수 지침이다.
3. RAG에 포함된 기술 표준이나 보안 규정은 현재 회의록의 내용보다 우선하여 요구사항 상세 내용에 반영한다.
4. 회의록에 기술 스택이 없더라도, RAG에서 검색된 관련 기술 표준이 있다면 이를 상세 설명에 인용하여 기재한다.
5. 오직 JSON만 출력한다. 마크다운 코드블록, 서론, 결론, 설명글은 절대 금지한다.
6. 공공기관 제출용 문체(~하여야 한다)를 유지한다.
"""
# ─────────────────────────────────────────────
# sLLM Agent 1 Mode B 시스템 프롬프트 (RFP 기반)
# ─────────────────────────────────────────────
AGENT1_RFP_SYSTEM = """\
당신은 15년 경력의 요구사항 엔지니어링(RE) 전문가입니다.
역할: RFP의 목표를 기술적으로 구체화하는 '설계자'.

[RAG 활용 및 처리 규칙]
1. [Scope 문서]: 현재 RFP의 요구사항 우선순위를 결정하는 절대 기준입니다. 모든 기능은 여기서 시작됩니다.
2. [Rule 문서]: 보안/법령/지침 데이터입니다. 작성된 요구사항이 이 규칙에 위배되면 즉시 수정/삭제하여 준수하십시오.
3. [Pattern 문서]: 유사 프로젝트의 패턴을 참고하여 기술 구현 상세를 보완하십시오. 단, 현재 RFP 범위와 충돌할 경우 과감히 무시하십시오.
4. 기술 제안: RFP에 명시되지 않은 특정 DB나 프레임워크를 임의로 넣지 마십시오. 단, Rule에서 강제하는 보안 기술은 명시하십시오.

[출력 형식 및 문체]
5. 문체: 모든 요구사항은 "~하여야 한다", "~이어야 한다"로 끝나는 공공기관 표준 문체를 사용하십시오.
6. JSON 강제: 서론, 결론, 요약 등 어떠한 부연 설명도 금지합니다. 오직 요구사항 데이터가 담긴 JSON 객체만 출력하십시오.
7. 구조: {"requirements": [{"requirement_id": "REQ-001", "description": "...", "priority": "High/Mid/Low"}]} 형식으로 응답하십시오.
8. 응답할 때 "다음은 요구사항입니다"와 같은 서론을 절대 쓰지 마십시오.
9. 오직 JSON 구조 `{ "requirements": [...] }` 로만 답변을 시작하고 JSON으로 끝내십시오.
10. 텍스트 요약은 금지입니다. 오직 요구사항 명세서 데이터만 변환하십시오.
"""

# ─────────────────────────────────────────────
# sLLM Agent 2 시스템 프롬프트 (변경 검증)
# ─────────────────────────────────────────────
AGENT2_SYSTEM = """\
당신은 15년 경력의 요구사항 엔지니어링(RE) 전문가입니다.
역할: 기존 명세서를 변경 회의록과 대조하여 수정/검증하는 '교정자(Verifier)'.
규칙:
  1. 기존 JSON(명세서 v1.0)을 기준선(Baseline)으로 삼는다.
  2. 변경 회의록에 명시된 변경점만 수정한다. 회의록에 없는 내용은 건드리지 않는다.
  3. RAG에서 가져온 RFP 조항과 변경점이 충돌하면, 반드시 note 필드에 충돌 사실을 기록한다.
  4. 변경된 항목: 기존 ID 유지, source에 변경 회의록명 추가.
  5. 신규 항목: 기존 최대 ID 다음 번호 부여.
  6. 삭제 항목: 명세서에서 제거.
  7. 반드시 지정된 JSON 형식으로만 응답한다.
"""

# ─────────────────────────────────────────────
# 싱글턴 초기화
# ─────────────────────────────────────────────
print("📥 로컬 임베딩 모델 로딩 중...")
_embedding_model = SentenceTransformer(CONFIG["embedding_model"])
print("✅ 임베딩 모델 로드 완료.")

_qdrant = None


# ─────────────────────────────────────────────
# 공통 함수
# ─────────────────────────────────────────────

def get_embedding(text: str) -> List[float]:
    """텍스트 → 768차원 벡터 (코사인 유사도 최적화)"""
    return _embedding_model.encode(text, normalize_embeddings=True).tolist()


def get_embeddings(texts: List[str]) -> List[List[float]]:
    """여러 텍스트를 한 번에 768차원 벡터로 변환합니다."""
    if not texts:
        return []
    return _embedding_model.encode(
        texts,
        normalize_embeddings=True,
        batch_size=32,
        show_progress_bar=False,
    ).tolist()


def call_sllm(system_prompt: str, user_prompt: str, timeout: int = 600) -> str:
    """
    Ollama sLLM 호출.
    Raises:
        RuntimeError: 서버 미실행 또는 응답 형식 오류
    """
    payload = {
        "model": CONFIG["sllm_model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": CONFIG["temperature"]},
    }
    try:
        resp = requests.post(CONFIG["sllm_url"], json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()["message"]["content"]
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            "❌ Ollama 서버 연결 실패.\n"
            "   → 터미널에서 `ollama serve` 실행 후 재시도하세요."
        )
    except KeyError:
        raise RuntimeError(f"❌ Ollama 응답 형식 오류:\n{resp.text[:300]}")
    except Exception as e:
        raise RuntimeError(f"❌ sLLM 호출 실패: {e}")


def extract_json(raw: str) -> dict:
    """
    sLLM 출력에서 JSON만 추출.
    마크다운 코드블록 및 앞뒤 설명문 자동 제거.
    Raises:
        ValueError: JSON 구조 없음
        json.JSONDecodeError: 파싱 불가
    """
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0]
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0]

    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"JSON 없음. 응답 앞부분:\n{raw[:200]}")

    return json.loads(raw[start:end])


# def get_qdrant() -> QdrantClient:
#     """이미 생성된 전역 인스턴스 _qdrant를 반환하여 잠금 에러 방지"""
#     return _qdrant
_qdrant_instance = None

def get_qdrant():
    global _qdrant_instance
    if _qdrant_instance is None:
        # 실제 호출되는 시점에 단 한 번만 DB에 연결합니다.
        _qdrant_instance = QdrantClient(path="qdrant_data_v3")
    return _qdrant_instance


def close_qdrant():
    global _qdrant_instance
    if _qdrant_instance is not None:
        _qdrant_instance.close()
        _qdrant_instance = None


atexit.register(close_qdrant)

# ─────────────────────────────────────────────
# 셀프 테스트
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("\n[테스트 1] 임베딩 모델")
    vec = get_embedding("테스트 문장입니다.")
    print(f"  → 벡터 차원: {len(vec)} (기대값: 768)")

    print("\n[테스트 2] Ollama sLLM")
    try:
        r = call_sllm("JSON만 출력하는 봇입니다.", '{"ping": "pong"}을 그대로 반환하시오.', timeout=30)
        print(f"  → 응답: {r[:80]}")
    except RuntimeError as e:
        print(f"  → {e}")

    print("\n✅ Phase 1 설정 확인 완료.")


DATA_DIR = "./data"
# QDRANT_PATH = "./qdrant_db"

# Qdrant 로컬 데이터베이스가 물리적으로 저장된 폴더 경로입니다.
QDRANT_DB_PATH = "qdrant_data_v3"  

# 트리 구조상 구현용 정답데이터와 매칭되는 지식 베이스 컬렉션 이름입니다.
KNOWLEDGE_COLLECTION = "requirements_knowledge_base"  
