"""
[PHASE 1-B] RFP → 회의록 생성기
=================================
지금은 RFP 문서만 있고 회의록이 없는 상황입니다.
이 파일은 RFP를 분석하여 두 종류의 회의록을 sLLM으로 생성합니다.

생성하는 회의록 종류:
  1. 착수 회의록   : "회의록.txt"      → Agent 1 Mode A의 입력
  2. 변경 회의록   : "변경_회의록.txt" → Agent 2의 입력

[기존 phase2_generate_minutes.py에서 수정한 내용]
  ❌ 문제 1: pages 10~20 하드코딩 → RFP 구조와 무관하게 엉뚱한 페이지 읽을 수 있음
     ✅ 수정:  전체 텍스트 추출 후 max_chars로 토큰 한도 조절
  ❌ 문제 2: call_sllm import 누락 및 시스템 프롬프트가 너무 단순
     ✅ 수정:  phase1_config의 call_sllm 사용, 구체적 작성 지침 추가
  ❌ 문제 3: 착수 회의록만 생성 (변경 회의록 없음)
     ✅ 수정:  generate_change_minutes() 추가

실행 방법:
  python phase1b_generate_minutes.py

의존성:
  phase1_config.py, phase1a_doc_reader.py
"""

import os
from pathlib import Path

from phase1_config import call_sllm
from phase1a_회의록용_rfp_parser import read_document


# ─────────────────────────────────────────────
# 1. 착수 회의록 생성
# ─────────────────────────────────────────────
def generate_kickoff_minutes(
    rfp_path: str,
    output_path: str = "data/회의록.txt",
    max_rfp_chars: int = 4000,
) -> str:
    """
    RFP 전문을 읽어 프로젝트 착수 회의록을 생성합니다.
    생성된 회의록은 Agent 1 Mode A (회의록 → 명세서 생성)의 입력으로 사용됩니다.
    
    착수 회의록에 포함되는 내용:
      - 회의 일시, 참석자 (개발팀장, PM, QA팀장, DB담당)
      - RFP에서 도출된 핵심 기능 목록
      - 기술 스택 논의 결과
      - 팀별 우려 사항 및 제약 조건
      - 향후 Action Item (담당자, 기한 포함)
    
    Args:
        rfp_path     : RFP 파일 경로 (PDF/DOCX/HWP 모두 가능)
        output_path  : 결과 저장 경로
        max_rfp_chars: sLLM에 전달할 RFP 텍스트 최대 길이
                       너무 길면 컨텍스트 초과, 너무 짧으면 내용 누락.
                       RFP 규모에 따라 2000~6000 조정.
    Returns:
        생성된 회의록 텍스트
    """
    print(f"📄 RFP 파일 읽는 중: {rfp_path}")
    rfp_text = read_document(rfp_path, max_chars=max_rfp_chars)
    print(f"   → {len(rfp_text):,}자 추출 완료")
    
    system_prompt = """\
당신은 경험 많은 프로젝트 PM입니다.
아래 RFP 내용을 분석하여 개발팀·기획팀·QA팀이 참여하는 프로젝트 착수 회의록을 작성하세요.

작성 규칙:
1. 회의록은 실제 회의에서 나온 대화 형식(누가 어떤 말을 했는지)으로 작성한다.
2. RFP에 명시된 기능과 제약 조건을 반드시 언급한다.
3. 각 참석자(PM, 개발팀장, QA, DB담당)는 자신의 관점에서 우려 사항을 제기한다.
4. 기술 스택 선택, 일정, 제약사항에 대한 실질적 논의를 포함한다.
5. 마지막에 Action Item을 '담당자: 할일 (기한)' 형식으로 정리한다.
6. 한국어로 작성하되, 기술 용어는 영어를 혼용해도 된다.
"""
    
    user_prompt = f"""\
아래 RFP를 분석하여 프로젝트 착수 회의록을 작성하시오.
회의 일시는 2026년 5월 30일 오후 2시로 설정하고,
참석자는 이기획(PM), 김개발(개발팀장), 박QA(QA팀장), 정DB(데이터팀)으로 구성하시오.

[RFP 내용]
{'='*60}
{rfp_text}
{'='*60}

위 RFP를 바탕으로 상세한 착수 회의록을 작성하시오.
"""
    
    print("🤖 착수 회의록 생성 중... (sLLM 호출)")
    minutes = call_sllm(system_prompt, user_prompt, timeout=240)
    
    # 저장
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(minutes)
    
    print(f"✅ 착수 회의록 저장 완료: {output_path} ({len(minutes):,}자)")
    return minutes


# ─────────────────────────────────────────────
# 2. 변경 회의록 생성
# ─────────────────────────────────────────────
def generate_change_minutes(
    rfp_path: str,
    existing_requirements_json_path: str,
    output_path: str = "data/RFP_변경_회의록.txt",
    max_rfp_chars: int = 2000,
) -> str:
    """
    RFP + 기존 명세서를 보고 현실적인 변경 회의록을 생성합니다.
    생성된 변경 회의록은 Agent 2 (수정/검증)의 입력으로 사용됩니다.
    
    변경 회의록에 포함되는 내용:
      - 발주처 담당자가 제기하는 변경 요청 (성능 강화, 기능 추가 등)
      - 개발팀이 제시하는 기술적 현실과 제약
      - 최종 합의된 변경사항 목록 (항목별 명확히)
    
    Args:
        rfp_path                      : 원본 RFP 파일
        existing_requirements_json_path: Agent 1이 생성한 요구사항 JSON 파일
        output_path                   : 결과 저장 경로
        max_rfp_chars                 : RFP 요약 길이 (변경 회의록은 더 짧아도 됨)
    Returns:
        생성된 변경 회의록 텍스트
    """
    import json
    
    # RFP 요약 추출
    print(f"📄 RFP 파일 읽는 중: {rfp_path}")
    rfp_summary = read_document(rfp_path, max_chars=max_rfp_chars)
    
    # 기존 명세서 로드 (있는 경우)
    existing_req_text = ""
    if existing_requirements_json_path and os.path.exists(existing_requirements_json_path):
        with open(existing_requirements_json_path, "r", encoding="utf-8") as f:
            existing_data = json.load(f)
        # 요구사항 이름 목록만 추출 (컨텍스트 절약)
        req_names = [
            f"{r['requirement_id']}: {r['requirement_name']}"
            for r in existing_data.get("requirements", [])
        ]
        existing_req_text = f"\n[현재 요구사항 명세서 목록]\n" + "\n".join(req_names)
        print(f"   → 기존 명세서: {len(req_names)}개 요구사항 로드")
    else:
        print("   ⚠️  기존 명세서 없음 (Agent 1 결과 없이 변경 회의록 생성)")
    
    system_prompt = """\
당신은 프로젝트 발주처(고객사) 담당자입니다.
개발팀과 함께 진행 중인 프로젝트의 요구사항 변경 회의를 진행합니다.
현실적이고 구체적인 변경 요청이 담긴 회의록을 작성하세요.

작성 규칙:
1. 발주처 담당자(최발주)가 구체적인 변경 사항을 요구한다 (성능 수치, 기능 추가, 방식 변경).
2. 개발팀장(김개발)은 기술적 타당성과 일정 영향을 현실적으로 검토한다.
3. PM(이기획)은 양측을 조율하며 최종 합의를 도출한다.
4. 마지막에 합의된 변경사항 목록을 '변경 항목: 변경 내용 (변경 전 → 변경 후)' 형식으로 정리한다.
5. 최소 3가지 이상의 변경/추가 요청을 포함한다.
6. 한국어로 작성한다.
"""
    
    user_prompt = f"""\
원본 RFP 내용과 현재 명세서를 검토하여 변경 회의록을 작성하시오.
회의 일시: 2026년 7월 15일 오전 10시
참석자: 최발주(발주처 담당), 이기획(PM), 김개발(개발팀장)

[원본 RFP 요약]
{'='*60}
{rfp_summary}
{'='*60}
{existing_req_text}

위 내용을 바탕으로, 발주처가 초기 계획에서 변경을 요청하는 현실적인 회의록을 작성하시오.
변경 요청은 성능 강화, 기능 추가, 방식 변경 등 다양하게 포함하시오.
"""
    
    print("🤖 변경 회의록 생성 중... (sLLM 호출)")
    minutes = call_sllm(system_prompt, user_prompt, timeout=240)
    
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(minutes)
    
    print(f"✅ 변경 회의록 저장 완료: {output_path} ({len(minutes):,}자)")
    return minutes


# ─────────────────────────────────────────────
# 실행 진입점
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    
    # RFP 파일 경로 (PDF/HWP/DOCX 모두 가능)
    # 실제 파일로 교체하세요
    RFP_FILE = "data/RFP_원본.pdf"       # ← 실제 RFP 파일 경로로 변경
    EXISTING_REQ = "output/agent1_requirements.json"
    
    if not os.path.exists(RFP_FILE):
        print(f"❌ RFP 파일 없음: {RFP_FILE}")
        print("   → 실제 RFP 파일 경로를 이 스크립트 하단의 RFP_FILE 변수에 입력하세요.")
        print("   → 또는 phase2_sample_data.py를 먼저 실행하여 샘플 데이터를 생성하세요.")
        sys.exit(1)
    
    print("=" * 55)
    print("  [PHASE 1-B] RFP → 회의록 생성")
    print("=" * 55)
    
    # 1. 착수 회의록 생성
    print("\n▶ Step 1: 착수 회의록 생성 (Agent 1 Mode A 입력용)")
    generate_kickoff_minutes(
        rfp_path=RFP_FILE,
        output_path="data/회의록.txt",
        max_rfp_chars=4000,
    )
    
    # 2. 변경 회의록 생성 (Agent 1 결과가 있으면 참조, 없어도 생성 가능)
    print("\n▶ Step 2: 변경 회의록 생성 (Agent 2 입력용)")
    generate_change_minutes(
        rfp_path=RFP_FILE,
        existing_requirements_json_path=EXISTING_REQ if os.path.exists(EXISTING_REQ) else None,
        output_path="data/RFP_변경_회의록.txt",
        max_rfp_chars=2000,
    )
    
    print("\n🎉 Phase 1-B 완료!")
    print("   → 착수 회의록:  data/회의록.txt")
    print("   → 변경 회의록:  data/RFP_변경_회의록.txt")
    print("   다음 단계: python phase3_qdrant_setup.py")
