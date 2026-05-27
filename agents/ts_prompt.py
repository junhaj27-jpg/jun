import json
from typing import Any


SYSTEM_PROMPT = """
반드시 JSON만 출력하세요. 설명, 주석, 마크다운 코드블록은 출력하지 마세요.

당신은 CBD SW개발 표준 산출물 가이드(D10)에 따라 통합시험 시나리오를 생성하는 전문가입니다.
사용자 요구사항 정의서와 선택적으로 제공되는 UI 설계서를 입력받아 통합시험 시나리오 JSON을 생성합니다.

출력 JSON 스키마:
{
  "scenarios": [
    {
      "scenario_id": "TS-001",
      "scenario_name": "시험시나리오명",
      "scenario_description": "시험시나리오 설명",
      "test_cases": [
        {
          "test_case_id": "TC-001",
          "test_case_description": "시험케이스 설명",
          "test_procedure": ["절차1", "절차2"],
          "scenario_detail": "단계별 실행 시나리오",
          "note": null
        }
      ]
    }
  ],
  "cases": [
    {
      "round": 1,
      "scenario_id": "TS-001",
      "scenario_name": "시험시나리오명",
      "test_case_id": "TC-001",
      "sequence": 1,
      "process_content": "절차1",
      "test_item": "시험 데이터 및 수행내용",
      "precondition": null,
      "input_data": "문자열 입력값",
      "expected_result": "예상 결과",
      "screen_id": "",
      "test_result": null,
      "note": null
    }
  ]
}

생성 규칙:
- 하나의 요구사항마다 정상 케이스, 경계값 케이스, 예외 케이스를 포함합니다.
- expected_result는 validation_criteria를 우선 근거로 작성합니다.
- input_data는 반드시 문자열로 작성합니다.
- test_result는 설계 단계이므로 항상 null입니다.
- UI 설계서가 제공되면 screen_id는 입력받은 screen_id를 그대로 사용하고 임의 생성하지 않습니다.
- UI 설계서가 없거나 관련 화면이 없으면 screen_id는 빈 문자열로 둡니다.
- scenarios[*].test_cases[*].test_procedure 항목 수와 cases의 동일 test_case_id 행 수는 반드시 1:1로 일치해야 합니다.
""".strip()


FEW_SHOT_INPUT = """
{
  "requirements": [
    {
      "requirement_id": "REQ-001",
      "requirement_name": "로그인",
      "requirement_type": "기능",
      "description": "사용자는 아이디와 비밀번호로 로그인할 수 있어야 한다.",
      "constraints": ["비밀번호 5회 오류 시 계정 잠금"],
      "validation_criteria": [
        "정상 계정으로 로그인 성공 여부를 확인한다.",
        "비밀번호 오류 시 오류 메시지를 확인한다."
      ]
    }
  ],
  "ui_screens": [
    {
      "screen_id": "UI-LOGIN-001",
      "screen_name": "로그인",
      "process_contents": [
        {"requirement_basis": "REQ-001"}
      ]
    }
  ]
}
""".strip()


FEW_SHOT_OUTPUT = """
{
  "scenarios": [
    {
      "scenario_id": "TS-001",
      "scenario_name": "로그인 통합시험",
      "scenario_description": "사용자 인증 흐름과 예외 처리를 검증한다.",
      "test_cases": [
        {
          "test_case_id": "TC-001",
          "test_case_description": "정상 계정 로그인 성공",
          "test_procedure": ["로그인 화면 접속", "아이디와 비밀번호 입력", "로그인 버튼 클릭"],
          "scenario_detail": "정상 사용자가 인증 정보를 입력하여 메인 화면으로 진입하는지 확인한다.",
          "note": null
        }
      ]
    }
  ],
  "cases": [
    {
      "round": 1,
      "scenario_id": "TS-001",
      "scenario_name": "로그인 통합시험",
      "test_case_id": "TC-001",
      "sequence": 1,
      "process_content": "로그인 화면 접속",
      "test_item": "로그인 화면 표시 확인",
      "precondition": null,
      "input_data": "로그인 메뉴 선택",
      "expected_result": "로그인 화면이 표시된다.",
      "screen_id": "UI-LOGIN-001",
      "test_result": null,
      "note": null
    },
    {
      "round": 1,
      "scenario_id": "TS-001",
      "scenario_name": "로그인 통합시험",
      "test_case_id": "TC-001",
      "sequence": 2,
      "process_content": "아이디와 비밀번호 입력",
      "test_item": "정상 인증정보 입력",
      "precondition": null,
      "input_data": "user01 / valid-password",
      "expected_result": "입력값이 정상 표시된다.",
      "screen_id": "UI-LOGIN-001",
      "test_result": null,
      "note": null
    },
    {
      "round": 1,
      "scenario_id": "TS-001",
      "scenario_name": "로그인 통합시험",
      "test_case_id": "TC-001",
      "sequence": 3,
      "process_content": "로그인 버튼 클릭",
      "test_item": "로그인 성공 확인",
      "precondition": null,
      "input_data": "로그인 버튼 클릭",
      "expected_result": "인증 성공 후 메인 화면으로 이동한다.",
      "screen_id": "UI-LOGIN-001",
      "test_result": null,
      "note": null
    }
  ]
}
""".strip()


def _filter_screens_by_requirement(screens: list[dict[str, Any]], requirement_id: str) -> list[dict[str, Any]]:
    matched = []
    for screen in screens:
        for process_content in screen.get("process_contents", []):
            basis = process_content.get("requirement_basis", "")
            if requirement_id and requirement_id in basis:
                matched.append(screen)
                break
    return matched


def build_prompt(requirement_json: str, ui_screens: list[str] | None = None) -> list[dict[str, str]]:
    req_data = json.loads(requirement_json)

    if ui_screens:
        all_screens: list[dict[str, Any]] = []
        for screen_text in ui_screens:
            try:
                parsed = json.loads(screen_text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, list):
                all_screens.extend(parsed)
            elif isinstance(parsed, dict):
                all_screens.append(parsed)

        requirements = req_data.get("requirements", [])
        requirement_id = requirements[0].get("requirement_id", "") if requirements else ""
        filtered_screens = _filter_screens_by_requirement(all_screens, requirement_id)
        if filtered_screens:
            req_data["ui_screens"] = filtered_screens

    actual_input = json.dumps(req_data, ensure_ascii=False, indent=2)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": FEW_SHOT_INPUT},
        {"role": "assistant", "content": FEW_SHOT_OUTPUT},
        {"role": "user", "content": actual_input},
    ]
