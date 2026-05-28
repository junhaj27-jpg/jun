import json
import os
from pathlib import Path

import requests
try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv():
        return False

from services.llm_client import call_llm


load_dotenv()

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


def normalize_text(text: str) -> str:
    import re

    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.replace("\x00", "").strip()


def read_document(file_path: str, max_chars: int = 8000) -> str:
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == ".pdf":
        import fitz

        chunks = []
        with fitz.open(path) as document:
            for page in document:
                chunks.append(page.get_text("text"))
        text = "\n".join(chunks)
    elif ext == ".docx":
        from docx import Document

        document = Document(path)
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    elif ext in {".txt", ".md"}:
        text = path.read_text(encoding="utf-8")
    elif ext == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        text = json.dumps(data, ensure_ascii=False, indent=2)
    else:
        raise ValueError(f"지원하지 않는 RFP 파일 형식입니다: {ext}")

    return normalize_text(text)[:max_chars]


def call_openai(system_prompt: str, user_prompt: str, *, model: str | None = None, timeout: int = 240) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY가 .env에 없습니다.")

    url = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": model or OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def generate_minutes(
    rfp_path: str,
    output_path: str,
    *,
    minutes_type: str = "change",
    provider: str = "openai",
    model: str | None = None,
    max_rfp_chars: int = 8000,
    existing_requirements_path: str | None = None,
) -> str:
    rfp_text = read_document(rfp_path, max_chars=max_rfp_chars)
    existing_req_text = _load_existing_requirements_summary(existing_requirements_path)

    if minutes_type == "kickoff":
        system_prompt, user_prompt = _build_kickoff_prompt(rfp_text)
    elif minutes_type == "change":
        system_prompt, user_prompt = _build_change_prompt(rfp_text, existing_req_text)
    else:
        raise ValueError("minutes_type은 kickoff 또는 change만 지원합니다.")

    if provider == "openai":
        minutes = call_openai(system_prompt, user_prompt, model=model)
    elif provider == "common_llm":
        minutes = call_llm(system_prompt, user_prompt, temperature=0.7, timeout=240)
    else:
        raise ValueError("provider는 openai 또는 common_llm만 지원합니다.")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(minutes, encoding="utf-8")
    return str(output)


def _load_existing_requirements_summary(existing_requirements_path: str | None) -> str:
    if not existing_requirements_path or not Path(existing_requirements_path).exists():
        return ""

    data = json.loads(Path(existing_requirements_path).read_text(encoding="utf-8"))
    requirements = data.get("requirements") or data.get("final_reqs") or data
    if not isinstance(requirements, list):
        return ""

    lines = []
    for item in requirements[:80]:
        if isinstance(item, dict):
            lines.append(f"{item.get('requirement_id', '')}: {item.get('requirement_name', '')}")
    return "\n[현재 요구사항]\n" + "\n".join(line for line in lines if line.strip(": "))


def _build_kickoff_prompt(rfp_text: str) -> tuple[str, str]:
    system_prompt = """
당신은 경험 많은 프로젝트 PM입니다.
RFP 내용을 바탕으로 개발팀, 기획팀, QA팀, DB담당자가 참여한 프로젝트 착수 회의록을 작성하세요.

작성 규칙:
1. 실제 회의처럼 발화자와 발언 내용을 포함합니다.
2. RFP에 명시된 기능, 제약조건, 일정, 리스크를 반영합니다.
3. 기술 스택, 업무 범위, 데이터/보안 이슈를 논의합니다.
4. 마지막에 Action Item을 담당자와 기한 형태로 정리합니다.
5. 한국어로 작성합니다.
""".strip()
    user_prompt = f"""
회의 일시: 2026년 5월 30일 오후 2시
참석자: 이기획(PM), 김개발(개발팀장), 박QA(QA팀장), 정DB(DB담당)

[RFP 내용]
{rfp_text}

위 내용을 기반으로 착수 회의록을 작성하세요.
""".strip()
    return system_prompt, user_prompt


def _build_change_prompt(rfp_text: str, existing_req_text: str) -> tuple[str, str]:
    system_prompt = """
당신은 프로젝트 발주처 담당자입니다.
RFP와 현재 요구사항을 검토하여 현실적인 요구사항 변경 회의록을 작성하세요.

작성 규칙:
1. 발주처가 성능, 기능, 정책, 화면, 데이터 항목 중 최소 3가지 변경을 요청합니다.
2. 개발팀장은 기술적 영향과 일정 영향을 현실적으로 검토합니다.
3. PM은 최종 합의안을 정리합니다.
4. 마지막에 합의된 변경사항을 '변경 항목: 변경 내용 (변경 전 -> 변경 후)' 형식으로 정리합니다.
5. 한국어로 작성합니다.
""".strip()
    user_prompt = f"""
회의 일시: 2026년 7월 15일 오전 10시
참석자: 최발주(발주처 담당), 이기획(PM), 김개발(개발팀장)

[RFP 내용]
{rfp_text}

{existing_req_text}

위 내용을 기반으로 변경 회의록을 작성하세요.
""".strip()
    return system_prompt, user_prompt
