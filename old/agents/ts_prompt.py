SYSTEM_PROMPT = """
반드시 JSON만 출력하세요. 다른 텍스트는 절대 출력하지 마세요.

당신은 CBD SW개발 표준 산출물 가이드(D10)에 따라 통합시험 시나리오를 생성하는 전문가입니다.

## 역할
사용자 요구사항 정의서와 UI 설계서를 입력받아, CBD 표준 포맷의 통합시험 시나리오를 JSON 형식으로 생성합니다.

## 출력 규칙
1. 반드시 JSON만 출력합니다. 설명, 주석, 마크다운 코드블록(```)을 포함하지 않습니다.
2. 출력 JSON은 아래 스키마를 정확히 따릅니다.
3. null이 허용된 필드 외에는 반드시 값을 채웁니다.
4. test_result는 설계 단계이므로 항상 null로 출력합니다.

## 출력 스키마
```python
from pydantic import BaseModel, Field
from typing import List, Optional

class TestCaseInScenario(BaseModel):
    test_case_id: str = Field(..., description="시험케이스 ID (예: TC-001)")
    test_case_description: str = Field(..., description="시험케이스 간략 설명")
    test_procedure: List[str] = Field(..., description="수행 절차 목록. 각 항목이 cases의 process_content에 대응")
    scenario_detail: str = Field(..., description="각 단계별 실행 시나리오 설명")
    note: Optional[str] = Field(None, description="기타 고려사항")

class TestScenario(BaseModel):
    scenario_id: str = Field(..., description="시험시나리오 고유 ID (예: TS-001)")
    scenario_name: str = Field(..., description="시험시나리오명")
    scenario_description: str = Field(..., description="시험시나리오 간략 설명")
    test_cases: List[TestCaseInScenario] = Field(..., description="시나리오에 포함된 시험케이스 목록")

class TestCase(BaseModel):
    round: int = Field(..., description="시험 시나리오별 시험을 수행한 횟수")
    scenario_id: str = Field(..., description="상위 시험시나리오 ID 참조")
    scenario_name: str = Field(..., description="상위 시험시나리오명 참조")
    test_case_id: str = Field(..., description="시험케이스 ID. TestCaseInScenario의 test_case_id와 대응")
    sequence: int = Field(..., description="업무처리 순서번호. test_procedure 리스트의 인덱스에 대응")
    process_content: str = Field(..., description="업무처리 내용. TestCaseInScenario.test_procedure의 항목 1개에 대응")
    test_item: str = Field(..., description="시험 데이터 및 수행내용")
    precondition: Optional[str] = Field(None, description="시험 수행 사전조건")
    input_data: str = Field(..., description="입력값")
    expected_result: str = Field(..., description="성공 시 예상 결과")
    screen_id: str = Field(..., description="시험 수행 화면 ID. UI 설계서의 screen_id를 참조하여 작성")
    test_result: Optional[str] = Field(None, description="실제 시험을 수행한 결과를 기술, 설계단계에서는 미기술")
    note: Optional[str] = Field(None, description="기타 참조사항")

class TestScenarioDocument(BaseModel):
    scenarios: List[TestScenario]
    cases: List[TestCase]
```

## 생성 가이드
- 하나의 요구사항에 대해 정상 케이스, 경계값 케이스, 예외 케이스를 포함한 시험케이스를 생성합니다.
- expected_result는 요구사항의 validation_criteria를 기반으로 작성합니다.
- 첫 번째 케이스(정상 케이스)는 전체 절차를 포함합니다.
- 이후 케이스는 핵심 검증 포인트에 집중하고, 공통 선행 조건은 precondition에 명시합니다.
- input_data는 반드시 문자열(str)로 작성합니다. 리스트 형식으로 작성하지 않습니다. 입력값이 없는 경우에도 "확인 버튼 클릭" 또는 "화면 확인" 등 수행 동작을 문자열로 기술합니다.
- screen_id는 반드시 입력받은 UI 설계서의 screen_id 값을 그대로 사용합니다. 임의로 만들지 않습니다.
- UI 설계서에 없는 화면 ID는 사용하지 않습니다.

## cases 생성 필수 규칙 (절대 위반 금지)
- cases의 각 행은 scenarios의 test_procedure 항목 1개에 반드시 1:1로 대응됩니다.
- test_procedure가 N개이면 해당 test_case_id에 대응하는 cases 행도 반드시 N개입니다.
- test_procedure의 모든 항목이 cases에 빠짐없이 포함되어야 합니다. 절대 누락하지 마십시오.
- cases 생성 시 반드시 아래 절차를 따르십시오:
  1단계: scenarios의 각 test_case별로 test_procedure 항목 수를 셉니다.
  2단계: 해당 test_case_id로 cases 행을 test_procedure 항목 수만큼 빠짐없이 생성합니다.
  3단계: 생성 후 test_procedure 항목 수와 cases 행 수가 일치하는지 반드시 검토합니다.
- 예시: test_procedure가 ["절차1", "절차2", "절차3"] 이면 반드시 sequence 1, 2, 3 cases 행 3개를 모두 생성합니다. sequence 1만 생성하고 끝내는 것은 오류입니다.
"""

FEW_SHOT_INPUT = """
{
  "requirements": [
    {
      "requirement_id": "SSR-F01001",
      "requirement_name": "원화자금이체신청",
      "requirement_type": "기능",
      "description": "망 참가기관이 개설한 당좌예금계좌를 통해 자금 거래 결제를 처리하는 기능이다. 사용자는 화면에서 [출금계좌선택], [수취은행], [수취계좌번호], [이체금액], [이체비밀번호]를 입력하여 신청한다. 시스템은 이체 실행 전 출금계좌의 잔액 검증 및 1회 한도(10억)를 체크해야 하며, 거래 종료 즉시 입금완료·예약·대기 내역을 처리 시스템(DB)에 기록하고 수취 기관 앞으로 Push 알림을 통해 결제 결과를 실시간 통보해야 한다.",
      "source": ["RFP(개발요구서 4) : 2p", "프로젝트수행계획서(별첨3) : 11p"],
      "constraints": [
        "한국은행 망 참가기관 인증을 획득한 기관 세션만 접근 가능",
        "당좌예금계좌가 사전에 등록되어 있어야 함",
        "1회 이체 한도는 최대 10억 원으로 제한함"
      ],
      "priority": "상",
      "validation_criteria": [
        "사용자가 출금계좌 및 수취정보를 입력하고 이체 신청 시 오류 없이 결제가 완료되는가?",
        "잔액 부족 또는 10억 한도 초과 시 이체 신청이 차단되고 적절한 에러 메시지가 팝업으로 노출되는가?",
        "거래 완료 즉시 신청 기관 및 수취 기관의 화면에 결제 결과가 실시간 통보(Push)되는가?",
        "이체 종료 후 당좌예금계좌 잔액과 거래내역 테이블(Transaction)의 데이터 정합성이 일치하는가?"
      ],
      "note": "관양접속 후 Push 기능 구현 필요. 결제시스템 관리 총액결제관리 서브시스템 핵심 기능임."
    }
  ],
  "ui_screens": [
    {
      "screen_id": "SS-UI-010-01",
      "screen_name": "원화자금이체신청",
      "screen_type": "입력",
      "menu_path": "결제시스템관리/총액결제관리/원화자금이체신청",
      "screen_overview": "망 참가기관 담당자가 출금계좌, 수취은행, 수취계좌번호, 이체금액, 이체비밀번호를 입력하여 원화자금이체를 신청하는 화면이다. 잔액 및 한도 검증 후 이체 신청이 처리된다.",
      "process_contents": [
        {
          "no": 1,
          "title": "출금계좌 선택",
          "description": "사용자가 드롭다운에서 출금계좌를 선택하면 시스템이 해당 계좌의 현재 잔액을 조회하여 화면에 표시한다.",
          "requirement_basis": "SSR-F01001: 출금계좌선택 입력 항목"
        },
        {
          "no": 2,
          "title": "이체 정보 입력",
          "description": "수취은행, 수취계좌번호, 이체금액, 이체비밀번호를 입력한다. 이체금액 입력 시 1회 한도(10억) 초과 여부를 실시간으로 표시한다.",
          "requirement_basis": "SSR-F01001: 수취은행, 수취계좌번호, 이체금액, 이체비밀번호 입력 항목"
        },
        {
          "no": 3,
          "title": "이체 신청 처리",
          "description": "이체신청 버튼 클릭 시 잔액 부족 또는 1회 한도 초과 여부를 검증하고, 검증 실패 시 에러 팝업을 노출한다. 검증 통과 시 이체를 처리하고 결과 화면으로 이동한다.",
          "requirement_basis": "SSR-F01001: 잔액 검증 및 한도 체크, 에러 메시지 팝업"
        }
      ],
      "button_markers": [
        {
          "no": 1,
          "target_area": "이체신청 버튼",
          "x_ratio": 0.85,
          "y_ratio": 0.90
        }
      ]
    },
    {
      "screen_id": "SS-UI-010-02",
      "screen_name": "원화자금이체결과",
      "screen_type": "조회",
      "menu_path": "결제시스템관리/총액결제관리/원화자금이체신청",
      "screen_overview": "원화자금이체 신청이 완료된 후 결제 결과를 표시하는 화면이다. 이체 완료 내역과 함께 신청 기관 및 수취 기관에 Push 알림이 실시간으로 전송된 결과를 확인할 수 있다.",
      "process_contents": [
        {
          "no": 1,
          "title": "결제 결과 표시",
          "description": "이체 처리 완료 후 거래번호, 이체금액, 처리시각, 처리상태(입금완료/예약/대기)를 화면에 표시한다.",
          "requirement_basis": "SSR-F01001: 거래 종료 즉시 처리 내역 기록"
        },
        {
          "no": 2,
          "title": "Push 알림 발송 확인",
          "description": "신청 기관 및 수취 기관에 Push 알림이 정상 발송되었음을 화면 내 알림 발송 상태 영역에서 확인할 수 있다.",
          "requirement_basis": "SSR-F01001: 수취 기관 앞 Push 알림 실시간 통보"
        }
      ],
      "button_markers": [
        {
          "no": 1,
          "target_area": "확인 버튼 (이체신청 화면으로 복귀)",
          "x_ratio": 0.85,
          "y_ratio": 0.90
        }
      ]
    }
  ]
}
"""

FEW_SHOT_OUTPUT = """
{
  "scenarios": [
    {
      "scenario_id": "SS_IT_TS_010",
      "scenario_name": "원화자금이체신청",
      "scenario_description": "망 참가기관이 당좌예금계좌를 통해 자금 거래 결제를 신청하고, 잔액 및 한도 검증 후 결제 결과가 실시간으로 통보되는지 검증한다.",
      "test_cases": [
        {
          "test_case_id": "SS_IT_TC_010",
          "test_case_description": "정상 이체 신청",
          "test_procedure": [
            "원화자금이체 담당자가 시스템에 로그인한다.",
            "출금계좌, 수취은행, 수취계좌번호, 이체금액(5억), 이체비밀번호를 입력한다.",
            "이체 신청 버튼을 클릭한다.",
            "결제 완료 후 신청 기관 및 수취 기관 화면의 Push 알림을 확인한다."
          ],
          "scenario_detail": "잔액이 충분하고 1회 한도(10억) 이내인 정상 케이스에서 이체가 완료되고 결제 결과가 실시간으로 양 기관에 통보되는 시나리오",
          "note": null
        },
        {
          "test_case_id": "SS_IT_TC_020",
          "test_case_description": "한도 초과 이체 신청 차단",
          "test_procedure": [
            "출금계좌, 수취은행, 수취계좌번호, 이체금액(15억), 이체비밀번호를 입력한다.",
            "이체 신청 버튼을 클릭한다.",
            "에러 팝업 메시지를 확인한다."
          ],
          "scenario_detail": "1회 이체 한도(10억)를 초과한 금액 입력 시 이체 신청이 차단되고 적절한 에러 메시지가 팝업으로 노출되는 시나리오",
          "note": null
        },
        {
          "test_case_id": "SS_IT_TC_030",
          "test_case_description": "잔액 부족 이체 신청 차단",
          "test_procedure": [
            "출금계좌, 수취은행, 수취계좌번호, 이체금액(출금계좌 잔액 초과), 이체비밀번호를 입력한다.",
            "이체 신청 버튼을 클릭한다.",
            "에러 팝업 메시지를 확인한다."
          ],
          "scenario_detail": "출금계좌 잔액이 부족한 경우 이체 신청이 차단되고 적절한 에러 메시지가 팝업으로 노출되는 시나리오",
          "note": null
        }
      ]
    }
  ],
  "cases": [
    {
      "round": 1,
      "scenario_id": "SS_IT_TS_010",
      "scenario_name": "원화자금이체신청",
      "test_case_id": "SS_IT_TC_010",
      "sequence": 1,
      "process_content": "원화자금이체 담당자가 시스템에 로그인한다.",
      "test_item": "한국은행 망 참가기관 인증 세션으로 로그인",
      "precondition": "당좌예금계좌가 사전에 등록되어 있어야 하며, 출금계좌 잔액이 이체금액(5억) 이상이어야 한다.",
      "input_data": "사용자ID: test_user01, 비밀번호: ****",
      "expected_result": "로그인 성공 후 원화자금이체신청 화면으로 이동한다.",
      "screen_id": "SS-UI-010-01",
      "test_result": null,
      "note": null
    },
    {
      "round": 1,
      "scenario_id": "SS_IT_TS_010",
      "scenario_name": "원화자금이체신청",
      "test_case_id": "SS_IT_TC_010",
      "sequence": 2,
      "process_content": "출금계좌, 수취은행, 수취계좌번호, 이체금액(5억), 이체비밀번호를 입력한다.",
      "test_item": "이체 신청 입력 항목 정상 입력",
      "precondition": null,
      "input_data": "출금계좌: 012-34-567890, 수취은행: 우리은행, 수취계좌번호: 098-76-543210, 이체금액: 500,000,000, 이체비밀번호: ****",
      "expected_result": "입력 항목이 화면에 정상적으로 표시되며 Validation Check를 통과한다.",
      "screen_id": "SS-UI-010-01",
      "test_result": null,
      "note": null
    },
    {
      "round": 1,
      "scenario_id": "SS_IT_TS_010",
      "scenario_name": "원화자금이체신청",
      "test_case_id": "SS_IT_TC_010",
      "sequence": 3,
      "process_content": "이체 신청 버튼을 클릭한다.",
      "test_item": "이체 신청 처리 및 DB 기록 확인",
      "precondition": null,
      "input_data": "이체신청 버튼 클릭",
      "expected_result": "오류 없이 결제가 완료되며, 거래내역 테이블(Transaction)에 입금완료·예약·대기 내역이 즉시 기록된다.",
      "screen_id": "SS-UI-010-01",
      "test_result": null,
      "note": null
    },
    {
      "round": 1,
      "scenario_id": "SS_IT_TS_010",
      "scenario_name": "원화자금이체신청",
      "test_case_id": "SS_IT_TC_010",
      "sequence": 4,
      "process_content": "결제 완료 후 신청 기관 및 수취 기관 화면의 Push 알림을 확인한다.",
      "test_item": "결제 결과 실시간 Push 통보 확인",
      "precondition": null,
      "input_data": "Push 알림 수신 대기 상태 확인",
      "expected_result": "거래 완료 즉시 신청 기관 및 수취 기관의 화면에 결제 결과가 실시간으로 Push 통보된다.",
      "screen_id": "SS-UI-010-02",
      "test_result": null,
      "note": null
    },
    {
      "round": 1,
      "scenario_id": "SS_IT_TS_010",
      "scenario_name": "원화자금이체신청",
      "test_case_id": "SS_IT_TC_020",
      "sequence": 1,
      "process_content": "출금계좌, 수취은행, 수취계좌번호, 이체금액(15억), 이체비밀번호를 입력한다.",
      "test_item": "1회 한도(10억) 초과 금액 입력",
      "precondition": "로그인 완료 상태, 당좌예금계좌가 사전에 등록되어 있어야 한다.",
      "input_data": "출금계좌: 012-34-567890, 수취은행: 우리은행, 수취계좌번호: 098-76-543210, 이체금액: 1,500,000,000, 이체비밀번호: ****",
      "expected_result": "입력 항목이 화면에 표시된다.",
      "screen_id": "SS-UI-010-01",
      "test_result": null,
      "note": null
    },
    {
      "round": 1,
      "scenario_id": "SS_IT_TS_010",
      "scenario_name": "원화자금이체신청",
      "test_case_id": "SS_IT_TC_020",
      "sequence": 2,
      "process_content": "이체 신청 버튼을 클릭한다.",
      "test_item": "한도 초과 이체 신청 차단 여부 확인",
      "precondition": null,
      "input_data": "이체신청 버튼 클릭",
      "expected_result": "이체 신청이 차단되며 '1회 이체 한도(10억)를 초과하였습니다.' 에러 메시지가 팝업으로 노출된다.",
      "screen_id": "SS-UI-010-01",
      "test_result": null,
      "note": null
    },
    {
      "round": 1,
      "scenario_id": "SS_IT_TS_010",
      "scenario_name": "원화자금이체신청",
      "test_case_id": "SS_IT_TC_020",
      "sequence": 3,
      "process_content": "에러 팝업 메시지를 확인한다.",
      "test_item": "에러 팝업 노출 및 닫힘 동작 확인",
      "precondition": null,
      "input_data": "팝업 확인 버튼 클릭",
      "expected_result": "팝업 확인 버튼 클릭 시 팝업이 닫히고 이체신청 화면으로 복귀한다.",
      "screen_id": "SS-UI-010-01",
      "test_result": null,
      "note": null
    },
    {
      "round": 1,
      "scenario_id": "SS_IT_TS_010",
      "scenario_name": "원화자금이체신청",
      "test_case_id": "SS_IT_TC_030",
      "sequence": 1,
      "process_content": "출금계좌, 수취은행, 수취계좌번호, 이체금액(출금계좌 잔액 초과), 이체비밀번호를 입력한다.",
      "test_item": "출금계좌 잔액 초과 금액 입력",
      "precondition": "로그인 완료 상태, 당좌예금계좌가 사전에 등록되어 있어야 하며, 출금계좌 잔액이 이체금액보다 적어야 한다. (예: 잔액 1억, 이체금액 3억)",
      "input_data": "출금계좌: 012-34-567890, 수취은행: 우리은행, 수취계좌번호: 098-76-543210, 이체금액: 300,000,000 (잔액: 100,000,000), 이체비밀번호: ****",
      "expected_result": "입력 항목이 화면에 표시된다.",
      "screen_id": "SS-UI-010-01",
      "test_result": null,
      "note": null
    },
    {
      "round": 1,
      "scenario_id": "SS_IT_TS_010",
      "scenario_name": "원화자금이체신청",
      "test_case_id": "SS_IT_TC_030",
      "sequence": 2,
      "process_content": "이체 신청 버튼을 클릭한다.",
      "test_item": "잔액 부족 이체 신청 차단 여부 확인",
      "precondition": null,
      "input_data": "이체신청 버튼 클릭",
      "expected_result": "이체 신청이 차단되며 '출금계좌 잔액이 부족합니다.' 에러 메시지가 팝업으로 노출된다.",
      "screen_id": "SS-UI-010-01",
      "test_result": null,
      "note": null
    },
    {
      "round": 1,
      "scenario_id": "SS_IT_TS_010",
      "scenario_name": "원화자금이체신청",
      "test_case_id": "SS_IT_TC_030",
      "sequence": 3,
      "process_content": "에러 팝업 메시지를 확인한다.",
      "test_item": "에러 팝업 노출 및 닫힘 동작 확인",
      "precondition": null,
      "input_data": "팝업 확인 버튼 클릭",
      "expected_result": "팝업 확인 버튼 클릭 시 팝업이 닫히고 이체신청 화면으로 복귀한다.",
      "screen_id": "SS-UI-010-01",
      "test_result": null,
      "note": null
    }
  ]
}
"""


def _filter_screens_by_requirement(screens: list, requirement_id: str) -> list:
    """
    requirement_id와 연관된 화면만 필터링하여 반환합니다.

    각 화면의 process_contents[*].requirement_basis 필드에
    requirement_id 문자열이 포함된 화면만 선택합니다.

    매칭되는 화면이 없을 경우 빈 리스트를 반환합니다.
    """
    matched = []
    for screen in screens:
        for pc in screen.get("process_contents", []):
            basis = pc.get("requirement_basis", "")
            if requirement_id in basis:
                matched.append(screen)
                break  # 화면 하나에서 한 번 매칭되면 다음 화면으로
    return matched


def build_prompt(requirement_json: str, ui_screens: list[str] | None = None) -> list:
    """
    Few-shot 프롬프트를 구성하여 messages 리스트로 반환합니다.

    Args:
        requirement_json: 실제 input으로 사용할 요구사항 정의서 JSON 문자열 (요구사항 1개)
        ui_screens: UI 설계서 파트 2 JSON 파일들의 내용을 담은 문자열 리스트.
                    None이면 요구사항 정의서만으로 프롬프트를 구성합니다.
                    요구사항 ID를 기준으로 관련 화면만 필터링하여 토큰을 절약합니다.

    Returns:
        LLM API의 messages 파라미터에 전달할 리스트
    """
    import json

    req_data = json.loads(requirement_json)

    # 실제 input 구성: 요구사항 정의서 + UI 설계서(있는 경우)
    if ui_screens:
        # ui_screens 문자열 리스트를 파싱해서 전체 화면 배열로 합침
        all_screens = []
        for s in ui_screens:
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    all_screens.extend(parsed)
                else:
                    all_screens.append(parsed)
            except json.JSONDecodeError:
                pass

        # 요구사항 ID 추출 (요구사항 1개짜리 JSON이므로 첫 번째 항목)
        requirements = req_data.get("requirements", [])
        requirement_id = requirements[0].get("requirement_id", "") if requirements else ""

        # 관련 화면만 필터링
        filtered_screens = _filter_screens_by_requirement(all_screens, requirement_id)

        if filtered_screens:
            print(f"[INFO] UI 설계서 필터링: 전체 {len(all_screens)}개 → {requirement_id} 관련 {len(filtered_screens)}개")
        else:
            print(f"[INFO] UI 설계서 필터링: {requirement_id}에 매칭되는 화면 없음. UI 설계서 없이 진행.")

        if filtered_screens:
            req_data["ui_screens"] = filtered_screens

        actual_input = json.dumps(req_data, ensure_ascii=False, indent=2)
    else:
        actual_input = requirement_json.strip()

    return [
        {
            "role": "user",
            "content": FEW_SHOT_INPUT.strip()
        },
        {
            "role": "assistant",
            "content": FEW_SHOT_OUTPUT.strip()
        },
        {
            "role": "user",
            "content": actual_input
        }
    ]
