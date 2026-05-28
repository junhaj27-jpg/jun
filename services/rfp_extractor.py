import json
import re
from pathlib import Path
from typing import Any

from services.llm_client import call_llm
from services.minutes_generator import read_document


REQUIREMENT_ID_PATTERN = re.compile(
    r"\b((?:SFR|SIR|COR|CMR|FQR|SEC|PER|AST|GCL|ISR|DAR|WTR|UOR|PRM|OPS|MNG|CSR|ECR|TER|SER|INR|QUR|PMR|PSR)-?\d{3,5}|REQ-\d{3,5})\b",
    re.IGNORECASE,
)


def extract_rfp_to_json(
    rfp_path: str,
    output_path: str,
    *,
    max_chars: int = 16000,
    use_llm: bool = True,
) -> str:
    source_path = Path(rfp_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    if source_path.suffix.lower() == ".json":
        data = json.loads(source_path.read_text(encoding="utf-8"))
        normalized = normalize_requirement_document(data, source_path.name)
        output.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(output)

    rfp_text = read_document(str(source_path), max_chars=max_chars)
    requirements = []

    if use_llm:
        try:
            requirements = extract_requirements_with_llm(rfp_text, source_path.name)
        except Exception:
            requirements = []

    if not requirements:
        requirements = extract_requirements_by_rule(rfp_text, source_path.name)

    payload = {"requirements": requirements}
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(output)


def extract_requirements_with_llm(rfp_text: str, source_name: str) -> list[dict[str, Any]]:
    system_prompt = """
당신은 RFP에서 요구사항 정의서 초안을 추출하는 분석가입니다.
반드시 JSON만 출력하세요. 마크다운 코드블록이나 설명은 출력하지 마세요.
""".strip()
    user_prompt = f"""
아래 RFP 텍스트에서 요구사항을 추출하여 다음 스키마의 JSON으로 출력하세요.

출력 스키마:
{{
  "requirements": [
    {{
      "requirement_id": "REQ-001 또는 원문 요구사항 ID",
      "requirement_name": "요구사항명",
      "requirement_type": "기능 또는 비기능",
      "description": "요구사항 설명",
      "source": ["{source_name}"],
      "constraints": ["제약사항"],
      "priority": "상/중/하",
      "validation_criteria": ["검증 기준"],
      "note": null
    }}
  ]
}}

추출 규칙:
- 원문에 SFR, SIR, COR, SEC, PER 같은 요구사항 ID가 있으면 그대로 사용합니다.
- 원문 ID가 없으면 REQ-001부터 순차 부여합니다.
- 요구사항명은 업무/기능 중심으로 짧게 작성합니다.
- 검증 기준은 테스트 가능한 문장으로 작성합니다.
- source에는 반드시 "{source_name}"을 포함합니다.

[RFP 텍스트]
{rfp_text}
""".strip()
    raw = call_llm(system_prompt, user_prompt, temperature=0.2, timeout=600)
    parsed = _extract_json(raw)
    return normalize_requirement_document(parsed, source_name)["requirements"]


def extract_requirements_by_rule(rfp_text: str, source_name: str) -> list[dict[str, Any]]:
    matches = list(REQUIREMENT_ID_PATTERN.finditer(rfp_text))
    if not matches:
        return [
            {
                "requirement_id": "REQ-001",
                "requirement_name": "RFP 기반 요구사항",
                "requirement_type": "기능",
                "description": rfp_text[:3000],
                "source": [source_name],
                "constraints": _pick_lines(rfp_text, ["해야", "하여야", "필수", "반드시", "제한", "보안"]),
                "priority": "중",
                "validation_criteria": _pick_lines(rfp_text, ["확인", "검증", "지원", "제출", "가능"]),
                "note": "규칙 기반으로 추출된 초안입니다.",
            }
        ]

    requirements = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(rfp_text)
        block = rfp_text[start:end].strip()
        req_id = match.group(1).upper()
        requirements.append(
            {
                "requirement_id": req_id,
                "requirement_name": _guess_requirement_name(block, req_id),
                "requirement_type": _guess_requirement_type(req_id, block),
                "description": block[:3000],
                "source": [source_name],
                "constraints": _pick_lines(block, ["해야", "하여야", "필수", "반드시", "제한", "보안"]),
                "priority": "중",
                "validation_criteria": _pick_lines(block, ["확인", "검증", "지원", "제출", "가능"]),
                "note": "규칙 기반으로 추출된 초안입니다.",
            }
        )
    return requirements


def normalize_requirement_document(data: Any, source_name: str) -> dict[str, list[dict[str, Any]]]:
    if isinstance(data, list):
        requirements = data
    elif isinstance(data, dict):
        requirements = data.get("requirements") or data.get("final_reqs") or []
    else:
        requirements = []

    normalized = []
    for index, item in enumerate(requirements, start=1):
        if not isinstance(item, dict):
            continue
        req_id = item.get("requirement_id") or item.get("req_id") or f"REQ-{index:03d}"
        req_name = item.get("requirement_name") or item.get("name") or f"요구사항_{req_id}"
        description = item.get("description") or item.get("definition") or item.get("raw_text") or ""
        if isinstance(item.get("sub_details"), list):
            description = (description + "\n" + "\n".join(item["sub_details"])).strip()
        normalized.append(
            {
                "requirement_id": str(req_id),
                "requirement_name": str(req_name),
                "requirement_type": item.get("requirement_type") or "기능",
                "description": description,
                "source": item.get("source") if isinstance(item.get("source"), list) else [source_name],
                "constraints": _as_list(item.get("constraints")),
                "priority": item.get("priority") or "중",
                "validation_criteria": _as_list(item.get("validation_criteria")),
                "note": item.get("note"),
            }
        )
    return {"requirements": normalized}


def _extract_json(raw: str) -> Any:
    text = raw.strip()
    if text.startswith("```"):
        text = "\n".join(text.splitlines()[1:])
    if text.endswith("```"):
        text = text[:-3].strip()
    if not text.startswith("{") and not text.startswith("["):
        match = re.search(r"(\{.*\}|\[.*\])", text, flags=re.DOTALL)
        if match:
            text = match.group(1)
    return json.loads(text)


def _pick_lines(text: str, keywords: list[str], limit: int = 8) -> list[str]:
    lines = [line.strip(" -•·ㅇ■\t") for line in re.split(r"[\n\r]+", text) if line.strip()]
    picked = [line for line in lines if any(keyword in line for keyword in keywords)]
    return list(dict.fromkeys(picked))[:limit]


def _guess_requirement_name(block: str, req_id: str) -> str:
    first_line = next((line.strip() for line in block.splitlines() if line.strip()), "")
    first_line = first_line.replace(req_id, "").strip(" :-|")
    return first_line[:60] or f"요구사항_{req_id}"


def _guess_requirement_type(req_id: str, block: str) -> str:
    if req_id.startswith(("SEC", "PER", "QUR", "SIR")):
        return "비기능"
    if any(keyword in block for keyword in ["보안", "성능", "품질", "가용성", "접근성"]):
        return "비기능"
    return "기능"


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]
