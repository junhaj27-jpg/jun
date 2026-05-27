import os
import json
from pathlib import Path
from dotenv import load_dotenv

from openai import OpenAI

from phase1a_회의록용_rfp_parser import read_document

# ─────────────────────────────────────────────
# OpenAI Client
# ─────────────────────────────────────────────
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def call_openai(system_prompt: str, user_prompt: str, model: str = "gpt-4.1-mini") -> str:
    """
    OpenAI API 호출 래퍼
    """
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
    )
    return response.choices[0].message.content


# ─────────────────────────────────────────────
# 1. 착수 회의록 생성
# ─────────────────────────────────────────────
def generate_kickoff_minutes(
    rfp_path: str,
    output_path: str = "data/회의록.txt",
    max_rfp_chars: int = 4000,
) -> str:

    print(f"📄 RFP 파일 읽는 중: {rfp_path}")
    rfp_text = read_document(rfp_path, max_chars=max_rfp_chars)
    print(f"   → {len(rfp_text):,}자 추출 완료")

    system_prompt = """
당신은 경험 많은 프로젝트 PM입니다.
아래 RFP를 기반으로 실제 회의처럼 생생한 착수 회의록을 작성하세요.

규칙:
1. 반드시 대화형 회의록 (발화자 포함)
2. PM / 개발팀장 / QA / DB담당 의견 포함
3. RFP 기능 및 제약조건 반드시 반영
4. 기술 스택, 일정, 리스크 논의 포함
5. 마지막에 Action Item 정리
6. 한국어 작성 (기술용어 일부 영어 허용)
"""

    user_prompt = f"""
회의 일시: 2026년 5월 30일 오후 2시
참석자: 이기획(PM), 김개발(개발팀장), 박QA(QA팀장), 정DB(DB담당)

[RFP]
{rfp_text}

위 내용을 기반으로 착수 회의록을 작성하시오.
"""

    print("🤖 OpenAI 착수 회의록 생성 중...")
    minutes = call_openai(system_prompt, user_prompt)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(minutes)

    print(f"✅ 저장 완료: {output_path}")
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

    print(f"📄 RFP 파일 읽는 중: {rfp_path}")
    rfp_summary = read_document(rfp_path, max_chars=max_rfp_chars)

    existing_req_text = ""

    if existing_requirements_json_path and os.path.exists(existing_requirements_json_path):
        with open(existing_requirements_json_path, "r", encoding="utf-8") as f:
            existing_data = json.load(f)

        req_names = [
            f"{r['requirement_id']}: {r['requirement_name']}"
            for r in existing_data.get("requirements", [])
        ]

        existing_req_text = "\n[현재 요구사항]\n" + "\n".join(req_names)
        print(f"   → 기존 요구사항 {len(req_names)}개 로드")

    system_prompt = """
당신은 발주처 담당자입니다.
프로젝트 진행 중 현실적인 요구사항 변경 회의를 진행합니다.

규칙:
1. 발주처가 구체적인 변경 요청 (성능/기능/정책 변경)
2. 개발팀은 기술적 한계와 비용 설명
3. PM이 조율
4. 최소 3개 이상의 변경사항 포함
5. 마지막에 변경사항 정리 (Before → After)
6. 한국어 작성
"""

    user_prompt = f"""
회의일: 2026년 7월 15일 오전 10시
참석자: 최발주(발주처), 이기획(PM), 김개발(개발팀장)

[RFP 요약]
{rfp_summary}

{existing_req_text}

위 내용을 기반으로 변경 회의록을 작성하시오.
"""

    print("🤖 OpenAI 변경 회의록 생성 중...")
    minutes = call_openai(system_prompt, user_prompt)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(minutes)

    print(f"✅ 저장 완료: {output_path}")
    return minutes


# ─────────────────────────────────────────────
# 실행
# ─────────────────────────────────────────────
if __name__ == "__main__":

    RFP_FILE = r"C:\skn24\수업자료\08_large_language_model\00.final_project\data_pipeline\data\RFP\AI 기반 통합 플랫폼 구축 사업제안서.pdf"
    EXISTING_REQ = "output/agent1_requirements.json"

    if not os.path.exists(RFP_FILE):
        print(f"❌ RFP 없음: {RFP_FILE}")
        exit(1)

    print("=" * 60)
    print("[PHASE 1-B] RFP → 회의록 생성 (OpenAI)")
    print("=" * 60)

    print("\n▶ Step 1: 착수 회의록")
    generate_kickoff_minutes(RFP_FILE)

    print("\n▶ Step 2: 변경 회의록")
    generate_change_minutes(
        RFP_FILE,
        EXISTING_REQ if os.path.exists(EXISTING_REQ) else None
    )

    print("\n🎉 완료")