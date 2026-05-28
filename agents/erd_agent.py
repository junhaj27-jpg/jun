import os
import re
import json
from pathlib import Path
from datetime import date
from typing import Dict, Any

from dotenv import load_dotenv

from services.llm_client import call_llm
from rag.rag_service import build_erd_rag_context, compact_rag_context

load_dotenv()

REQ_JSON_PATH = os.getenv("REQ_JSON_PATH", "./data/requirements/requirement.json")


def extract_json_from_text(text: str) -> Dict[str, Any]:
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))

    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))

    raise ValueError("LLM 응답에서 JSON을 찾지 못했습니다.")


def call_qwen_for_erd(requirement: Dict[str, Any], rag_context: Dict[str, Any]) -> Dict[str, Any]:
    compact_context = compact_rag_context(rag_context)

    system_prompt = """
너는 SI 프로젝트의 데이터 모델러이자 ERD 설계서 작성 에이전트다.
입력으로 요구사항 JSON과 RAG 검색 결과가 주어진다.

너의 임무:
1. 요구사항에서 엔티티 후보를 도출한다.
2. 공공DB 표준화 관리 매뉴얼 RAG를 참고하여 표준화 기준을 반영한다.
3. 테이블명/컬럼명/데이터 타입/길이는 공공데이터 공통표준 RAG를 최대한 참고한다.
4. ERD 설계서에 들어갈 수 있는 JSON만 출력한다.
5. 설명 문장, 마크다운, 코드블록 없이 JSON 객체만 출력한다.

반드시 아래 JSON 스키마를 지켜라.

{
  "system_name": "시스템명",
  "stage_name": "설계",
  "created_date": "YYYY-MM-DD",
  "version": "v1.0",
  "erd_id": "ERD-요구사항ID",
  "erd_name": "ERD명",
  "requirement_id": "요구사항ID",
  "requirement_name": "요구사항명",
  "entities": [
    {
      "entity_id": "ENT-001",
      "entity_name": "테이블명_영문대문자",
      "entity_description": "엔티티 설명",
      "columns": [
        {
          "name": "컬럼명_영문대문자",
          "synonym": "한글명",
          "type": "VARCHAR|NUMBER|DECIMAL|DATE|DATETIME|CHAR|TEXT",
          "length": "길이",
          "not_null": "Y 또는 빈값",
          "pk": "Y 또는 빈값",
          "fk": "Y 또는 빈값",
          "inx": "Y 또는 빈값",
          "default": "기본값 또는 빈값",
          "constraint": "제약조건 설명"
        }
      ]
    }
  ],
  "relationships": [
    {
      "from_entity": "부모 엔티티명",
      "to_entity": "자식 엔티티명",
      "relationship": "1:1|1:N|N:M",
      "description": "관계 설명"
    }
  ]
}

주의:
- 엔티티는 최대 5개, 엔티티당 컬럼은 최대 12개로 제한한다.
- PK 컬럼은 반드시 포함한다.
- FK가 필요한 경우 FK 컬럼을 포함한다.
- 금액은 DECIMAL 또는 NUMBER 계열로 설계한다.
- 일시/일자는 DATE 또는 DATETIME으로 설계한다.
- 상태값은 코드성 컬럼으로 설계한다.
- 비밀번호는 원문 저장이 아니라 암호화/해시 저장 제약조건을 적는다.
- 컬럼명은 가능한 표준 단어를 조합한 영문 대문자 스네이크 케이스로 작성한다.
""".strip()

    user_prompt = {
        "requirement": requirement,
        "rag_context": compact_context,
        "today": str(date.today()),
    }

    content = call_llm(
        system_prompt,
        json.dumps(user_prompt, ensure_ascii=False),
        temperature=0.1,
        max_tokens=4096,
    )
    return extract_json_from_text(content)


def fallback_rule_based_erd(requirement: Dict[str, Any]) -> Dict[str, Any]:
    description = requirement.get("description", "")
    validation = " ".join(requirement.get("validation_criteria", []))
    constraints = " ".join(requirement.get("constraints", []))
    all_text = f"{description} {validation} {constraints}"
    input_items = re.findall(r"\[([^\]]+)\]", description)

    def col(name, synonym, typ="VARCHAR", length="100", pk="", fk="", not_null="Y", constraint=""):
        return {
            "name": name,
            "synonym": synonym,
            "type": typ,
            "length": length,
            "not_null": not_null,
            "pk": pk,
            "fk": fk,
            "inx": "Y" if pk == "Y" or fk == "Y" else "",
            "default": "",
            "constraint": constraint,
        }

    entities = []

    if "계좌" in all_text:
        entities.append({
            "entity_id": "ENT-001",
            "entity_name": "ACCOUNT",
            "entity_description": "계좌 정보를 관리하는 엔티티",
            "columns": [
                col("ACCOUNT_ID", "계좌ID", "VARCHAR", "50", pk="Y", constraint="계좌 고유 식별자"),
                col("ACCOUNT_NO", "계좌번호", "VARCHAR", "50", constraint="계좌번호"),
                col("ACCOUNT_TYPE_CODE", "계좌유형코드", "VARCHAR", "20", constraint="계좌 유형 코드"),
                col("BALANCE_AMOUNT", "잔액금액", "DECIMAL", "15,0", constraint="계좌 현재 잔액"),
                col("BANK_CODE", "은행코드", "VARCHAR", "20", constraint="은행 식별 코드"),
                col("CREATED_AT", "생성일시", "DATETIME", "", constraint="데이터 생성 일시"),
                col("UPDATED_AT", "수정일시", "DATETIME", "", constraint="데이터 수정 일시"),
            ],
        })

    if "이체" in all_text or "결제" in all_text:
        columns = [col("TRANSFER_ID", "이체ID", "VARCHAR", "50", pk="Y", constraint="이체 신청 고유 식별자")]

        for item in input_items:
            if item == "출금계좌선택":
                columns.append(col("WITHDRAW_ACCOUNT_ID", item, "VARCHAR", "50", fk="Y", constraint="출금 계좌 참조"))
            elif item == "수취은행":
                columns.append(col("RECEIVER_BANK_CODE", item, "VARCHAR", "20", constraint="수취 은행 코드"))
            elif item == "수취계좌번호":
                columns.append(col("RECEIVER_ACCOUNT_NO", item, "VARCHAR", "50", constraint="수취 계좌번호"))
            elif item == "이체금액":
                columns.append(col("TRANSFER_AMOUNT", item, "DECIMAL", "15,0", constraint="이체 요청 금액"))
            elif item == "이체비밀번호":
                columns.append(col("TRANSFER_PASSWORD_HASH", item, "VARCHAR", "255", constraint="이체비밀번호 해시값 저장"))

        columns.extend([
            col("TRANSFER_LIMIT_AMOUNT", "이체한도금액", "DECIMAL", "15,0", constraint="1회 이체 한도"),
            col("TRANSFER_STATUS_CODE", "이체상태코드", "VARCHAR", "20", constraint="완료/예약/대기/실패 상태 코드"),
            col("REQUESTED_AT", "신청일시", "DATETIME", "", constraint="이체 신청 일시"),
            col("COMPLETED_AT", "완료일시", "DATETIME", "", not_null="", constraint="이체 완료 일시"),
        ])

        entities.append({
            "entity_id": "ENT-002",
            "entity_name": "TRANSFER_REQUEST",
            "entity_description": "원화자금이체 신청 및 처리 상태를 관리하는 엔티티",
            "columns": columns[:12],
        })

    if "거래내역" in all_text or "Transaction" in all_text or "transaction" in all_text:
        entities.append({
            "entity_id": "ENT-003",
            "entity_name": "TRANSACTION",
            "entity_description": "이체 처리 후 발생한 거래내역을 기록하는 엔티티",
            "columns": [
                col("TRANSACTION_ID", "거래ID", "VARCHAR", "50", pk="Y", constraint="거래내역 고유 식별자"),
                col("TRANSFER_ID", "이체ID", "VARCHAR", "50", fk="Y", constraint="이체 신청 참조"),
                col("ACCOUNT_ID", "계좌ID", "VARCHAR", "50", fk="Y", constraint="계좌 참조"),
                col("TRANSACTION_AMOUNT", "거래금액", "DECIMAL", "15,0", constraint="거래 금액"),
                col("TRANSACTION_TYPE_CODE", "거래유형코드", "VARCHAR", "20", constraint="입금/출금 코드"),
                col("TRANSACTION_STATUS_CODE", "거래상태코드", "VARCHAR", "20", constraint="완료/예약/대기 상태 코드"),
                col("TRANSACTION_AT", "거래일시", "DATETIME", "", constraint="거래 발생 일시"),
            ],
        })

    if "Push" in all_text or "알림" in all_text or "통보" in all_text:
        entities.append({
            "entity_id": "ENT-004",
            "entity_name": "PUSH_NOTIFICATION",
            "entity_description": "결제 결과 실시간 통보 정보를 관리하는 엔티티",
            "columns": [
                col("NOTIFICATION_ID", "알림ID", "VARCHAR", "50", pk="Y", constraint="알림 고유 식별자"),
                col("TRANSFER_ID", "이체ID", "VARCHAR", "50", fk="Y", constraint="이체 신청 참조"),
                col("TARGET_INSTITUTION_CODE", "대상기관코드", "VARCHAR", "20", constraint="수신 기관 코드"),
                col("MESSAGE_CONTENT", "메시지내용", "TEXT", "", constraint="Push 알림 메시지"),
                col("SEND_STATUS_CODE", "발송상태코드", "VARCHAR", "20", constraint="성공/실패/대기 코드"),
                col("SENT_AT", "발송일시", "DATETIME", "", constraint="Push 발송 일시"),
            ],
        })

    entity_names = {e["entity_name"] for e in entities}
    relationships = []

    if "ACCOUNT" in entity_names and "TRANSFER_REQUEST" in entity_names:
        relationships.append({"from_entity": "ACCOUNT", "to_entity": "TRANSFER_REQUEST", "relationship": "1:N", "description": "하나의 계좌는 여러 이체 신청의 출금계좌로 사용될 수 있다."})
    if "TRANSFER_REQUEST" in entity_names and "TRANSACTION" in entity_names:
        relationships.append({"from_entity": "TRANSFER_REQUEST", "to_entity": "TRANSACTION", "relationship": "1:N", "description": "하나의 이체 신청은 하나 이상의 거래내역으로 기록될 수 있다."})
    if "TRANSFER_REQUEST" in entity_names and "PUSH_NOTIFICATION" in entity_names:
        relationships.append({"from_entity": "TRANSFER_REQUEST", "to_entity": "PUSH_NOTIFICATION", "relationship": "1:N", "description": "하나의 이체 신청 결과는 여러 기관에 Push 알림으로 통보될 수 있다."})

    return {
        "system_name": "CBD 자금이체 시스템",
        "stage_name": "설계",
        "created_date": str(date.today()),
        "version": "v1.0",
        "erd_id": "ERD-" + requirement.get("requirement_id", "REQ-001"),
        "erd_name": requirement.get("requirement_name", "요구사항") + " ERD",
        "requirement_id": requirement.get("requirement_id", ""),
        "requirement_name": requirement.get("requirement_name", ""),
        "entities": entities[:5],
        "relationships": relationships,
    }


def generate_erd_json_from_requirement(requirement: Dict[str, Any], use_llm: bool = True) -> Dict[str, Any]:
    print("[1] RAG 검색 시작")
    rag_context = build_erd_rag_context(requirement)
    print("[2] RAG 검색 완료")

    if use_llm:
        try:
            print("[3] LLM 호출 시작")
            erd = call_qwen_for_erd(requirement, rag_context)
            print("[4] LLM 호출 완료")
            return erd
        except Exception as e:
            print(f"[LLM 호출 실패] rule-based fallback 사용: {e}")

    print("[5] rule-based ERD 생성")
    return fallback_rule_based_erd(requirement)


def generate_erd_json(requirement_json_path: str = REQ_JSON_PATH, use_llm: bool = True) -> Dict[str, Any]:
    with open(requirement_json_path, "r", encoding="utf-8") as f:
        requirement_doc = json.load(f)

    requirements = requirement_doc.get("requirements", [])
    if not requirements:
        raise ValueError("requirements가 비어 있습니다.")

    erd = generate_erd_json_from_requirement(requirements[0], use_llm=use_llm)

    Path("./json_temp").mkdir(exist_ok=True)
    with open("./json_temp/erd_agent_output.json", "w", encoding="utf-8") as f:
        json.dump(erd, f, ensure_ascii=False, indent=2)

    return erd


if __name__ == "__main__":
    generate_erd_json(use_llm=True)
    print("[완료] ERD JSON: ./json_temp/erd_agent_output.json")
