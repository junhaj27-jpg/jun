import json


ANALYZE_SYSTEM = """\
당신은 요구사항 분석 전문가입니다.
RFP와 회의록에서 RAG 검색에 사용할 핵심 주제/키워드를 추출하십시오.
반드시 JSON만 출력: {"topics": ["주제1", "주제2"]}
"""

GENERATION_SYSTEM = """\
당신은 15년 경력의 요구사항 엔지니어링(RE) 전문가입니다.
RFP 요구사항과 회의록을 함께 분석하여 요구사항 명세서를 생성합니다.

[규칙]
1. RFP는 범위와 목표의 절대 기준이다.
2. 회의록은 RFP를 구체화하는 세부 요건이다.
3. RAG Rule 문서는 절대 위배 금지. 충돌 시 note에 기록.
4. RAG Pattern 문서는 참고용. RFP 범위 충돌 시 무시.
5. 공공기관 문체(~하여야 한다)를 사용한다.
6. 오직 JSON만 출력한다.
"""

REFINE_SYSTEM = """\
당신은 요구사항 검토 전문가입니다.
초안 요구사항의 누락/중복/모순을 검토하고 수정하십시오.

[규칙]
1. RFP 범위를 벗어난 항목은 제거한다.
2. 중복 항목은 하나로 통합한다.
3. 모순 항목은 RFP 기준으로 수정한다.
4. 오직 JSON만 출력한다.
"""


MODIFY_SYSTEM = """\
당신은 15년 경력의 요구사항 엔지니어링(RE) 전문가입니다.
기존 요구사항 명세서를 수정 지시에 따라 교정하는 역할입니다.

[핵심 규칙]
1. [기존 요구사항]을 기준선(Baseline)으로 삼는다.
2. [수정 지시]에 명시된 내용만 수정한다. 언급 없는 항목은 절대 건드리지 않는다.
3. 변경 항목: 기존 requirement_id를 반드시 유지한다.
4. 신규 항목: requirement_id를 빈 문자열("")로 두면 자동 발급된다.
5. 삭제 항목: 응답 JSON에서 제외한다.
6. RAG 데이터와 충돌 시: note 필드에 충돌 내용을 반드시 기록한다.
7. 공공기관 문체(~하여야 한다)를 사용한다.
8. 오직 JSON만 출력한다.
"""

_FMT = """\
아래 JSON 구조로만 응답하라. 마크다운(```) 절대 금지.
{
  "requirements": [{
    "requirement_id": "기존ID 유지 (신규는 빈 문자열)",
    "requirement_name": "요구사항명",
    "requirement_type": "기능",
    "description": "상세 설명 (~하여야 한다)",
    "source": ["출처문서명"],
    "constraints": [],
    "priority": "상",
    "validation_criteria": ["검증 기준"],
    "note": null
  }]
}
허용값: requirement_type → "기능"|"비기능" / priority → "상"|"중"|"하"
"""

# ── 유저 프롬프트 빌더 ────────────────────────────────────

def build_analyze_prompt(rfp: list[dict], cleaned_minutes: str) -> str:
    return f"[RFP]\n{json.dumps(rfp, ensure_ascii=False)}\n\n[회의록]\n{cleaned_minutes}"

def build_pass1_prompt(rfp, cleaned_minutes, rag_context) -> str:
    return f"""{_FMT}
[RFP 요구사항]
{json.dumps(rfp, ensure_ascii=False, indent=2)}

[회의록]
{cleaned_minutes}

[RAG 데이터]
{rag_context}"""

def build_pass2_prompt(rfp, cleaned_minutes, rag_context, draft_reqs) -> str:
    return f"""{_FMT}
[RFP 요구사항]
{json.dumps(rfp, ensure_ascii=False, indent=2)}

[회의록]
{cleaned_minutes}

[RAG 데이터]
{rag_context}

[초안 요구사항]
{json.dumps(draft_reqs, ensure_ascii=False, indent=2)}"""

def build_modify_prompt(existing_reqs: list[dict], instruction: str, rag_context: str) -> str:
    return f"""{_FMT}
[기존 요구사항]
{json.dumps(existing_reqs, ensure_ascii=False, indent=2)}

[수정 지시]
{instruction}

[RAG 데이터]
{rag_context}"""