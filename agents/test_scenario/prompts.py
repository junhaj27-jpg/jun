# 통합시험 시나리오 생성과 정제에 사용하는 프롬프트와 보조 유틸입니다.

import json
import os
import re
from pathlib import Path
from typing import Any


TS_RAW_OUTPUT_DIR = os.getenv("TS_RAW_OUTPUT_DIR", "./storage/temp/ts_raw_outputs")
TS_REQUIREMENT_MAX_CHARS = int(os.getenv("TS_REQUIREMENT_MAX_CHARS", "1800"))
TS_FIELD_MAX_CHARS = int(os.getenv("TS_FIELD_MAX_CHARS", "500"))

DROP_KEYS = {"raw_text", "full_text", "page_text", "chunks", "tables", "pages", "embedding", "vector"}


CBD_TS_SYSTEM_PROMPT = """
반드시 JSON만 출력하세요. 설명, 주석, 마크다운 코드블록(```json 등)은 절대 금지합니다.
응답의 첫 글자는 반드시 { 또는 [ 이어야 합니다.

당신은 CBD SW개발 표준 산출물 가이드(D10)에 따라 통합시험 시나리오를 생성하는 전문가입니다.
사용자 요구사항 정의서와 UI 설계서를 입력받아 통합시험 시나리오를 JSON 형식으로 생성합니다.

공통 규칙:
- 정상 케이스, 경계값/입력값 검증 케이스, 예외 케이스, 권한 검증, 상태 변경, 데이터 정합성 검증을 고려합니다.
- expected_result는 요구사항의 validation_criteria와 UI description을 기반으로 작성합니다.
- 입력값은 반드시 문자열로 작성합니다. 예: "아이디: user01, 비밀번호: pass1234"
- 예상결과는 반드시 문자열로 작성합니다. 예: "로그인 성공 메시지가 표시되고 메인 화면으로 이동한다."
- 처리내용은 반드시 문자열로 작성합니다. 예: "로그인 폼에 아이디와 비밀번호를 입력하고 로그인 버튼을 클릭한다."
- 사전조건은 반드시 문자열로 작성합니다. 예: "시스템에 정상 접근 가능한 상태이어야 한다."
- input_data 또는 입력값은 반드시 문자열로 작성합니다. dict나 list 형태로 작성하지 않습니다.
- test_result는 설계 단계이므로 항상 null 또는 빈 값으로 둡니다.
- UI 설계서에 없는 화면 ID를 임의로 만들지 않습니다. 없으면 빈 문자열 또는 N/A를 사용합니다.
- test_procedure가 N개이면 해당 test_case_id에 대응하는 step도 N개 생성합니다.
- 출력 JSON은 요청한 최상위 키만 포함합니다.
- 경계값/예외 케이스의 입력값은 실제 데이터를 전부 나열하지 말고 "500자 이상의 텍스트", "길이 제한 초과 데이터"처럼 설명 형태로 간략히 작성합니다.
- 동일 문자나 숫자를 반복해서 입력값을 구성하지 않습니다.

권장 출력 필드:
- scenario: scenario_id, scenario_name, scenario_description, source_requirement_ids
- test_case_json_list: test_case_id, scenario_id, case_type, test_case_name, test_procedure, source_requirement_ids
- step_json_list 또는 step_detail_json: test_case_id, step_no, 처리내용, 시험항목, 사전조건, 입력값, 예상결과, 화면ID, test_result
""".strip()


SCENARIO_GENERATION_PROMPT = (
    CBD_TS_SYSTEM_PROMPT
    + "\n\n요구사항별 업무 시험 시나리오를 JSON으로 생성하세요. "
    "JSON으로 scenario 또는 scenario_json_list만 반환하세요."
)

TEST_CASE_GENERATION_PROMPT = (
    CBD_TS_SYSTEM_PROMPT
    + "\n\n시나리오별 통합시험 케이스를 생성하세요. "
    "각 test_case에는 test_procedure 배열을 포함하고, 정상/경계값/예외/권한/상태변경/데이터정합성을 고려하세요. "
    "case_type은 반드시 다음 6개 중 하나만 사용하세요: "
    "NORMAL, EXCEPTION, AUTHORIZATION, INPUT_VALIDATION, STATE_CHANGE, DATA_INTEGRITY. "
    "이 6개 외의 case_type(예: 보안, 성능, 사용성 등)은 절대 생성하지 마세요. "
    "시나리오 하나당 test_case는 최대 6개로 제한하세요. "
    "JSON으로 test_case_json_list를 반환하세요."
)

STEP_SKELETON_PROMPT = (
    CBD_TS_SYSTEM_PROMPT
    + "\n\n시험케이스별 시험 절차를 생성하세요. "
    "test_procedure의 각 항목마다 step을 하나씩 생성하세요. "
    "반드시 최상위 키가 step_json_list인 JSON만 반환하세요. "
    "scenario, test_case_json_list 등 다른 키는 포함하지 않습니다. "
    "예: {\"step_json_list\": [{\"step_no\": 1, \"처리내용\": \"...\", ...}]}"
)

STEP_DETAIL_PROMPT = (
    CBD_TS_SYSTEM_PROMPT
    + "\n\nStep별 상세 시험 정보를 생성하세요. "
    "입력으로 주어진 처리내용(처리내용 또는 process 필드)은 절대 변경하지 말고 그대로 유지하세요. "
    "입력값은 \"유효한 시험 데이터\", \"유효하지 않은 시험 데이터\"처럼 모호하게 작성하지 말고, "
    "처리내용과 시험항목에 맞는 구체적인 값(예: 실제 입력 텍스트, 파라미터, 요청 본문 형태)으로 반드시 작성하세요. "
    "단, 경계값/예외 케이스의 입력값은 공통 규칙에 따라 설명 형태로 간략히 작성합니다. "
    "시험항목, 사전조건, 입력값, 예상결과, 화면ID를 "
    "reference_interface_json_list를 활용하여 채우고 JSON으로 step_detail_json을 반환하세요. "
    "입력으로 주어진 step은 이미 하나의 단일 step입니다. 새로운 시나리오나 시험 케이스를 "
    "만들지 말고, 이 step 하나에 대한 상세 정보만 채우세요. "
    "반드시 최상위 키가 step_detail_json인 JSON 객체만 반환하세요. "
    "scenario, test_case_json_list, step_json_list 등 다른 키나 중첩 구조는 절대 포함하지 않습니다. "
    "예: {\"step_detail_json\": {\"step_no\": 1, \"처리내용\": \"...\", \"시험항목\": \"...\", "
    "\"사전조건\": \"...\", \"입력값\": \"...\", \"예상결과\": \"...\", \"화면ID\": \"...\"}}"
)

SCENARIO_SUMMARY_PROMPT = (
    "당신은 CBD SW개발 표준 산출물 가이드(D10)에 따라 통합시험 시나리오 문서를 정리하는 전문가입니다. "
    "다음은 하나의 시험 케이스에 속한 시험 절차(처리내용) 목록입니다. "
    "이 절차들의 핵심 내용을 하나의 문장으로 요약하세요.\n\n"
    "규칙:\n"
    "- 절차가 1개이면 해당 절차 문장의 어미만 명사형으로 바꾸세요.\n"
    "- 절차가 여러 개이면 전체 내용을 하나의 문장으로 요약한 뒤 명사형으로 종결하세요.\n"
    "- 문장은 반드시 명사형으로 끝내야 합니다(예: '~검증', '~확인', '~처리', '~점검').\n"
    "- '~한다', '~된다', '~된다.' 같은 동사형 종결은 절대 사용하지 마세요.\n"
    "- 설명, 주석, 마크다운 코드블록은 금지합니다. 응답의 첫 글자는 반드시 { 이어야 합니다.\n\n"
    "반드시 JSON으로 {\"summary\": \"...\"} 형식만 반환하세요."
)


def compact_requirement_for_ts(requirement: dict[str, Any]) -> dict[str, Any]:
    preferred_keys = [
        "req_id",
        "req_name",
        "requirement_id",
        "requirement_name",
        "requirement_type",
        "type",
        "detail_text",
        "description",
        "source",
        "source_refs",
        "constraints",
        "priority",
        "validation_criteria",
        "note",
    ]
    compacted = {
        key: _compact_value(requirement.get(key))
        for key in preferred_keys
        if key in requirement
    }
    if len(json.dumps(compacted, ensure_ascii=False)) <= TS_REQUIREMENT_MAX_CHARS:
        return compacted
    for key in ("source", "constraints", "validation_criteria", "detail_text", "description", "note"):
        if key in compacted:
            compacted[key] = _compact_value(compacted[key], max(TS_FIELD_MAX_CHARS // 2, 250))
        if len(json.dumps(compacted, ensure_ascii=False)) <= TS_REQUIREMENT_MAX_CHARS:
            break
    return compacted


def compact_payload_for_ts(value: Any) -> Any:
    return _compact_value(value)


def save_raw_output(stage: str, identifier: str, raw_output: Any) -> str:
    output_dir = Path(TS_RAW_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_id = re.sub(r"[^0-9A-Za-z가-힣_.-]+", "_", str(identifier or "unknown"))[:80]
    output_path = output_dir / f"{stage}_{safe_id or 'unknown'}_raw_output.txt"
    output_path.write_text(str(raw_output), encoding="utf-8")
    return str(output_path)


def _compact_value(value: Any, max_chars: int = TS_FIELD_MAX_CHARS) -> Any:
    if isinstance(value, str):
        return _truncate_text(value, max_chars)
    if isinstance(value, list):
        compacted = []
        current_chars = 0
        for item in value:
            compacted_item = _compact_value(item, max_chars)
            item_chars = len(json.dumps(compacted_item, ensure_ascii=False))
            if compacted and current_chars + item_chars > max_chars:
                compacted.append("...(길이 제한으로 나머지 항목 생략)")
                break
            compacted.append(compacted_item)
            current_chars += item_chars
        return compacted
    if isinstance(value, dict):
        return {
            key: _compact_value(item, max_chars)
            for key, item in value.items()
            if key not in DROP_KEYS
        }
    return value


def _truncate_text(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n...(길이 제한으로 일부 생략)"
