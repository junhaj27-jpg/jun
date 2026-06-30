# TS DOCX 문서의 시나리오/케이스/Step 표를 TS Agent 입력용 JSON으로 변환합니다.

import re
from pathlib import Path
from typing import Any

from tools.parser.docx_parser import parse_docx
from tools.result import ToolResult, error_result, success_result


def parse_ts_docx(file_path: str) -> ToolResult:
    """TS(통합시험 시나리오) DOCX를 파싱하여 구조화된 JSON을 반환합니다.

    Returns:
        ToolResult with data containing:
        - scenario_json_list
        - test_case_json_list
        - step_json_list
        - step_detail_json_list
    """
    parsed = parse_docx(file_path)
    if not parsed["success"]:
        return parsed

    raw_tables = parsed["data"].get("tables") or []
    if not raw_tables:
        return error_result(
            "TS_DOCX_TABLES_NOT_FOUND",
            "TS DOCX에서 테이블을 찾지 못했습니다.",
            {"file_path": str(Path(file_path))},
        )

    result = _extract_ts_data(raw_tables)
    if not result["scenario_json_list"]:
        return error_result(
            "TS_DOCX_SCENARIO_NOT_FOUND",
            "TS DOCX에서 시나리오 테이블을 찾지 못했습니다.",
            {"file_path": str(Path(file_path))},
        )

    return success_result(
        {
            "file_path": parsed["data"].get("file_path", str(Path(file_path))),
            **result,
        }
    )


def _extract_ts_data(raw_tables: list[Any]) -> dict[str, list[dict[str, Any]]]:
    """raw 테이블 목록을 시나리오/케이스/step 구조로 분류·추출합니다."""
    scenarios: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    step_details: list[dict[str, Any]] = []

    step_counter = 0
    current_scenario_id = ""

    for raw_table in raw_tables:
        rows = _clean_rows(raw_table)
        if not rows:
            continue

        col_count = max(len(row) for row in rows)

        # 헤더 테이블 (6열, 첫 행에 "통합시험" 포함) → 건너뜀
        if col_count == 6 and _contains(rows[0], "통합시험"):
            continue

        # 시나리오 테이블 (5열, 첫 셀에 "시험시나리오" 포함)
        if col_count == 5 and _contains_cell(rows, 0, 0, "시험시나리오"):
            scenario = _parse_scenario_table(rows)
            if scenario:
                scenarios.append(scenario)
                current_scenario_id = scenario.get("scenario_id", "")
                # 시나리오 테이블 행4+에 있는 케이스 요약도 수집
                case_summaries = _parse_case_summaries_from_scenario(rows, current_scenario_id)
                for summary in case_summaries:
                    # 케이스 테이블에서 더 상세한 정보가 오면 병합됨
                    existing = next(
                        (c for c in cases if c["test_case_id"] == summary["test_case_id"]),
                        None,
                    )
                    if not existing:
                        cases.append(summary)
            continue

        # 케이스 테이블 (9열, "차수" 또는 "시험시나리오" 포함)
        if col_count == 9 and (
            _contains_cell(rows, 0, 0, "차수") or _contains_cell(rows, 1, 0, "시험시나리오")
        ):
            case, case_steps = _parse_case_table(rows, step_counter)
            if case:
                # 시나리오 테이블에서 온 요약 정보와 병합
                existing = next(
                    (c for c in cases if c["test_case_id"] == case["test_case_id"]),
                    None,
                )
                if existing:
                    existing.update({k: v for k, v in case.items() if v})
                else:
                    cases.append(case)

                for step in case_steps:
                    step_counter += 1
                    step["step_id"] = f"STEP-{step_counter:04d}"
                    step["step_detail_id"] = f"STEP-DTL-{step_counter:04d}"
                    steps.append(step)
                    step_details.append(_to_step_detail(step, step_counter))
            continue

    return {
        "scenario_json_list": scenarios,
        "test_case_json_list": cases,
        "step_json_list": steps,
        "step_detail_json_list": step_details,
    }


def _parse_scenario_table(rows: list[list[str]]) -> dict[str, Any] | None:
    """시나리오 테이블(5열)에서 시나리오 정보를 추출합니다.

    구조:
        행0: 시험시나리오 ID | (merged) | SCN-XXX | ...
        행1: 시험시나리오명   | (merged) | value   | ...
        행2: 시험시나리오설명 | (merged) | value   | ...
        행3: 헤더 (시험케이스 ID | 시험케이스 설명 | 시험 절차 | 시나리오 설명 | 비고)
        행4+: 케이스 요약 행
    """
    if len(rows) < 4:
        return None

    scenario_id = _first_value_after_label(rows[0], "시험시나리오")
    scenario_name = _first_value_after_label(rows[1], "시험시나리오")
    scenario_description = _first_value_after_label(rows[2], "시험시나리오")

    if not scenario_id:
        return None

    return {
        "scenario_id": scenario_id,
        "scenario_name": scenario_name or "",
        "scenario_description": scenario_description or "",
        "source_requirement_ids": [],
    }


def _parse_case_summaries_from_scenario(
    rows: list[list[str]],
    scenario_id: str,
) -> list[dict[str, Any]]:
    """시나리오 테이블의 행4+에서 케이스 요약 정보를 추출합니다.

    구조 (행3이 헤더):
        시험케이스 ID | 시험케이스 설명 | 시험 절차 | 시나리오 설명 | 비고
    """
    summaries: list[dict[str, Any]] = []
    if len(rows) < 5:
        return summaries

    for row in rows[4:]:
        case_id = _cell(row, 0)
        if not case_id or _is_header_text(case_id):
            continue

        summaries.append({
            "test_case_id": case_id,
            "scenario_id": scenario_id,
            "test_case_name": _cell(row, 1),
            "case_type": _infer_case_type(_cell(row, 1), _cell(row, 3)),
            "test_procedure": _parse_procedure_text(_cell(row, 2)),
            "scenario_description_summary": _cell(row, 3),
        })

    return summaries


def _parse_case_table(
    rows: list[list[str]],
    step_offset: int,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """케이스 테이블(9열)에서 케이스 정보와 step 목록을 추출합니다.

    구조:
        행0: 차수            | (merged) | (빈 칸, 사용자 기입)
        행1: 시험시나리오 ID  | (merged) | SCN-XXX | ...
        행2: 시험시나리오명   | (merged) | value   | ...
        행3: 시험케이스 ID   | (merged) | case_id | ...
        행4: 시험 절차       | (merged) | 시험 항목 | 사전조건 | 입력자료 | 예상결과 | 화면 ID | 시험결과 | 비고
        행5: 순번 | 업무처리내용 | 시험 항목 | 사전조건 | 입력자료 | 예상결과 | 화면 ID | 시험결과 | 비고
        행6+: step detail 데이터
    """
    if len(rows) < 6:
        return None, []

    scenario_id = _first_value_after_label(rows[1], "시험시나리오")
    scenario_name = _first_value_after_label(rows[2], "시험시나리오")
    case_id = _first_value_after_label(rows[3], "시험케이스")

    if not case_id:
        return None, []

    # step detail 추출 (행6+)
    case_steps: list[dict[str, Any]] = []
    for row in rows[6:] if len(rows) > 6 else []:
        step = _parse_step_row(row, case_id, scenario_id)
        if step:
            case_steps.append(step)

    # test_procedure 재구성 (step들의 처리내용으로)
    test_procedure = [
        {
            "step_no": step.get("step_no"),
            "처리내용": step.get("처리내용", ""),
            "process": step.get("처리내용", ""),
        }
        for step in case_steps
    ]

    # case_type 추론: 케이스 이름이 없으므로 step의 시험항목으로 보완
    step_text = " ".join(s.get("시험항목", "") for s in case_steps)
    case = {
        "test_case_id": case_id,
        "scenario_id": scenario_id or "",
        "scenario_name": scenario_name or "",
        "test_case_name": "",
        "case_type": _infer_case_type(step_text, ""),
        "test_procedure": test_procedure,
    }

    return case, case_steps


def _parse_step_row(
    row: list[str],
    case_id: str,
    scenario_id: str,
) -> dict[str, Any] | None:
    """케이스 테이블의 데이터 행(행6+)에서 step 정보를 추출합니다.

    열 순서: 순번 | 업무처리내용 | 시험항목 | 사전조건 | 입력자료 | 예상결과 | 화면ID | 시험결과 | 비고
    """
    step_no_text = _cell(row, 0)
    process = _cell(row, 1)

    if not process or _is_header_text(step_no_text):
        return None

    step_no = _parse_int(step_no_text)

    return {
        "test_case_id": case_id,
        "scenario_id": scenario_id,
        "step_no": step_no,
        "처리내용": process,
        "process": process,
        "시험항목": _cell(row, 2),
        "test_item": _cell(row, 2),
        "사전조건": _cell(row, 3),
        "precondition": _cell(row, 3),
        "입력값": _cell(row, 4),
        "input_value": _cell(row, 4),
        "예상결과": _cell(row, 5),
        "expected_result": _cell(row, 5),
        "화면ID": _cell(row, 6),
        "screen_id": _cell(row, 6),
        "test_result": _cell(row, 7) or None,
    }


def _to_step_detail(step: dict[str, Any], index: int) -> dict[str, Any]:
    """step dict를 step_detail 형식으로 변환합니다."""
    return {
        "step_detail_id": step.get("step_detail_id", f"STEP-DTL-{index:04d}"),
        "step_id": step.get("step_id", f"STEP-{index:04d}"),
        "test_case_id": step.get("test_case_id", ""),
        "step_no": step.get("step_no", index),
        "처리내용": step.get("처리내용", ""),
        "시험항목": step.get("시험항목", ""),
        "사전조건": step.get("사전조건", ""),
        "입력값": step.get("입력값", ""),
        "예상결과": step.get("예상결과", ""),
        "화면ID": step.get("화면ID", ""),
        "screen_id": step.get("screen_id", ""),
    }


# ── 유틸리티 ──────────────────────────────────────────────────────


def _parse_procedure_text(text: str) -> list[dict[str, Any]]:
    """시나리오 테이블의 "시험 절차" 텍스트를 파싱합니다.
    "1. 첫 번째 절차\n2. 두 번째 절차" 형태를 리스트로 변환.
    """
    procedures = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        # "1. ", "2. " 같은 번호 접두사 제거
        cleaned = re.sub(r"^\d+\.\s*", "", line).strip()
        if cleaned:
            step_no = len(procedures) + 1
            procedures.append({
                "step_no": step_no,
                "처리내용": cleaned,
                "process": cleaned,
            })
    if not procedures and text.strip():
        procedures.append({
            "step_no": 1,
            "처리내용": text.strip(),
            "process": text.strip(),
        })
    return procedures


def _clean_rows(raw_table: Any) -> list[list[str]]:
    """raw 테이블 데이터를 정리된 문자열 행 목록으로 변환합니다."""
    rows: list[list[str]] = []
    if not isinstance(raw_table, list):
        return rows
    for raw_row in raw_table:
        if not isinstance(raw_row, list):
            continue
        row = [_clean_cell(cell) for cell in raw_row]
        if any(row):
            rows.append(row)
    return rows


def _clean_cell(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def _cell(row: list[str], index: int) -> str:
    if index >= len(row):
        return ""
    return row[index].strip()


def _contains(row: list[str], keyword: str) -> bool:
    return any(keyword in cell for cell in row)


def _contains_cell(rows: list[list[str]], row_idx: int, col_idx: int, keyword: str) -> bool:
    if row_idx >= len(rows):
        return False
    if col_idx >= len(rows[row_idx]):
        return False
    return keyword in rows[row_idx][col_idx]


def _first_value_after_label(row: list[str], label_keyword: str) -> str:
    """행에서 label_keyword를 포함하는 셀 이후의 첫 번째 고유한 값을 반환합니다.
    merged cell로 인해 label이 여러 셀에 반복될 수 있으므로, label과 다른 값을 찾습니다.
    """
    found_label = False
    label_texts: set[str] = set()
    for cell in row:
        text = cell.strip()
        if label_keyword in text:
            found_label = True
            label_texts.add(text)
        elif found_label and text and text not in label_texts:
            return text
    return ""


def _is_header_text(text: str) -> bool:
    headers = {"순번", "시험케이스", "시험시나리오", "차수", "시험 절차", "업무처리내용"}
    return any(h in text for h in headers)


def _infer_case_type(name: str, description: str) -> str:
    """케이스 이름/설명에서 case_type을 추론합니다.

    이전 세션에서 정의된 6종 화이트리스트 기준:
    NORMAL, EXCEPTION, BOUNDARY, PERFORMANCE, SECURITY, DATA_VALIDATION
    """
    text = f"{name} {description}".lower()

    if any(kw in text for kw in ("예외", "오류", "에러", "실패", "비정상", "장애", "fallback", "exception", "error")):
        return "EXCEPTION"
    if any(kw in text for kw in ("경계", "한계", "최대", "최소", "초과", "미만", "boundary", "limit")):
        return "BOUNDARY"
    if any(kw in text for kw in ("성능", "부하", "응답시간", "처리량", "동시", "performance", "load")):
        return "PERFORMANCE"
    if any(kw in text for kw in ("보안", "권한", "인증", "접근", "암호", "토큰", "비인가", "security", "auth")):
        return "SECURITY"
    if any(kw in text for kw in ("데이터", "유효성", "무결성", "일관성", "검증", "validation", "integrity")):
        return "DATA_VALIDATION"
    return "NORMAL"


def _parse_int(text: str) -> int:
    try:
        return int(text)
    except (ValueError, TypeError):
        return 0
