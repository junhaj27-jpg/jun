import os
import re
import json
from pathlib import Path
from datetime import date
from typing import Dict, Any, List

from dotenv import load_dotenv

from services.llm_client import call_llm
from rag.base_rag_service import compact_rag_context
from rag.erd_rag_service import build_erd_rag_context

load_dotenv()

REQ_JSON_PATH = os.getenv("REQ_JSON_PATH", "./data/requirements/requirement.json")


def _join_list(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value if item)
    return str(value or "")


def build_integrated_requirement(requirement_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Collapse all requirements into one system-level ERD input."""
    requirements = requirement_doc.get("requirements", [])
    if not requirements:
        raise ValueError("requirements가 비어 있습니다.")

    requirement_ids = [item.get("requirement_id", "") for item in requirements if item.get("requirement_id")]
    requirement_names = [item.get("requirement_name", "") for item in requirements if item.get("requirement_name")]

    sections: List[str] = []
    validation_sections: List[str] = []
    constraint_sections: List[str] = []
    source_sections: List[str] = []

    for item in requirements:
        req_id = item.get("requirement_id", "")
        req_name = item.get("requirement_name", "")
        prefix = f"[{req_id}] {req_name}".strip()
        sections.append(f"{prefix}\n{item.get('description', '')}".strip())
        validation_sections.append(f"{prefix}\n{_join_list(item.get('validation_criteria', []))}".strip())
        constraint_sections.append(f"{prefix}\n{_join_list(item.get('constraints', []))}".strip())
        source_sections.append(f"{prefix}\n{_join_list(item.get('source', []))}".strip())

    return {
        "requirement_id": "SYSTEM-ALL",
        "requirement_name": "전체 요구사항 기반 통합 ERD",
        "requirement_type": "통합",
        "description": "\n\n".join(section for section in sections if section),
        "source": source_sections,
        "constraints": constraint_sections,
        "priority": "통합",
        "validation_criteria": validation_sections,
        "note": requirement_doc.get("note", ""),
        "requirement_ids": requirement_ids,
        "requirement_names": requirement_names,
        "requirement_count": len(requirements),
    }


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
너는 SI 프로젝트의 데이터 모델러이자 통합 ERD 설계서 작성 에이전트다.
입력으로 전체 요구사항을 취합한 JSON과 RAG 검색 결과가 주어진다.

너의 임무:
1. 모든 requirements의 업무 기능, 데이터 항목, 검증 기준, 제약 조건을 종합한다.
2. 중복/유사 개념은 하나의 엔티티로 병합하고, 여러 요구사항에서 공유되는 공통 엔티티를 우선 도출한다.
3. 기능 하나의 화면/프로세스 ERD가 아니라 시스템 전체 관점의 논리 ERD를 설계한다.
4. 공공DB 표준화 관리 매뉴얼 RAG를 참고하여 표준화 기준을 반영한다.
5. 테이블명/컬럼명/데이터 타입/길이는 공공데이터 공통표준 RAG를 최대한 참고한다.
6. ERD 설계서에 들어갈 수 있는 JSON만 출력한다.
7. 설명 문장, 마크다운, 코드블록 없이 JSON 객체만 출력한다.

반드시 아래 JSON 스키마를 지켜라.

{
  "system_name": "시스템명",
  "stage_name": "설계",
  "created_date": "YYYY-MM-DD",
  "version": "v1.0",
  "erd_id": "ERD-SYSTEM-ALL",
  "erd_name": "통합 ERD명",
  "requirement_id": "SYSTEM-ALL",
  "requirement_name": "전체 요구사항 기반 통합 ERD",
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
- 전체 requirements에서 데이터 저장/관리 대상이 되는 핵심 업무 엔티티를 빠짐없이 도출한다.
- 일반적인 규모는 엔티티 8~25개, 엔티티당 컬럼 6~20개를 권장하되, 요구사항상 필요한 핵심 엔티티는 생략하지 않는다.
- 단일 기능에 치우치지 말고 포털, 사용자/권한, 문서/지식, AI 모델, 상담/대화, 분석, 배치/연계, 로그/감사 등 전체 업무 영역을 검토한다.
- requirement_ids가 제공되면 여러 요구사항을 포괄하는 통합 ERD로 작성한다.
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
    validation = _join_list(requirement.get("validation_criteria", []))
    constraints = _join_list(requirement.get("constraints", []))
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

    if "AI" in all_text or "인공지능" in all_text or "생성형" in all_text:
        entities.append({
            "entity_id": "ENT-001",
            "entity_name": "AI_MODEL",
            "entity_description": "AI 모델 및 배포 버전 정보를 관리하는 엔티티",
            "columns": [
                col("MODEL_ID", "모델ID", "VARCHAR", "50", pk="Y", constraint="AI 모델 고유 식별자"),
                col("MODEL_NAME", "모델명", "VARCHAR", "200", constraint="AI 모델 명칭"),
                col("MODEL_TYPE_CODE", "모델유형코드", "VARCHAR", "30", constraint="생성형/분류/검색 등 모델 유형"),
                col("MODEL_VERSION", "모델버전", "VARCHAR", "50", constraint="모델 버전"),
                col("DEPLOY_STATUS_CODE", "배포상태코드", "VARCHAR", "20", constraint="운영/검증/중지 상태 코드"),
                col("CREATED_AT", "생성일시", "DATETIME", "", constraint="데이터 생성 일시"),
                col("UPDATED_AT", "수정일시", "DATETIME", "", constraint="데이터 수정 일시"),
            ],
        })

    if "사용자" in all_text or "권한" in all_text or "관리자" in all_text:
        entities.append({
            "entity_id": "ENT-002",
            "entity_name": "USER_ACCOUNT",
            "entity_description": "사용자 계정과 인증 상태를 관리하는 엔티티",
            "columns": [
                col("USER_ID", "사용자ID", "VARCHAR", "50", pk="Y", constraint="사용자 고유 식별자"),
                col("LOGIN_ID", "로그인ID", "VARCHAR", "100", constraint="로그인 식별자"),
                col("USER_NAME", "사용자명", "VARCHAR", "100", constraint="사용자 이름"),
                col("PASSWORD_HASH", "비밀번호해시", "VARCHAR", "255", constraint="비밀번호 해시값 저장"),
                col("USER_STATUS_CODE", "사용자상태코드", "VARCHAR", "20", constraint="정상/잠금/탈퇴 상태 코드"),
                col("CREATED_AT", "생성일시", "DATETIME", "", constraint="데이터 생성 일시"),
            ],
        })
        entities.append({
            "entity_id": "ENT-003",
            "entity_name": "ROLE_PERMISSION",
            "entity_description": "역할별 권한 정보를 관리하는 엔티티",
            "columns": [
                col("ROLE_ID", "역할ID", "VARCHAR", "50", pk="Y", constraint="역할 고유 식별자"),
                col("ROLE_NAME", "역할명", "VARCHAR", "100", constraint="역할 명칭"),
                col("PERMISSION_CODE", "권한코드", "VARCHAR", "50", constraint="기능 접근 권한 코드"),
                col("USE_YN", "사용여부", "CHAR", "1", constraint="Y/N"),
                col("CREATED_AT", "생성일시", "DATETIME", "", constraint="데이터 생성 일시"),
            ],
        })

    if "문서" in all_text or "지식" in all_text or "RAG" in all_text or "검색" in all_text:
        entities.append({
            "entity_id": "ENT-004",
            "entity_name": "KNOWLEDGE_DOCUMENT",
            "entity_description": "지식 문서와 학습 원천 정보를 관리하는 엔티티",
            "columns": [
                col("DOCUMENT_ID", "문서ID", "VARCHAR", "50", pk="Y", constraint="문서 고유 식별자"),
                col("DOCUMENT_TITLE", "문서제목", "VARCHAR", "300", constraint="문서 제목"),
                col("DOCUMENT_TYPE_CODE", "문서유형코드", "VARCHAR", "30", constraint="규정/법률/업무자료 등 유형"),
                col("SOURCE_PATH", "원천경로", "VARCHAR", "500", constraint="원본 파일 또는 URL 경로"),
                col("INDEX_STATUS_CODE", "색인상태코드", "VARCHAR", "20", constraint="대기/완료/실패 상태 코드"),
                col("REGISTERED_AT", "등록일시", "DATETIME", "", constraint="문서 등록 일시"),
            ],
        })

    if "상담" in all_text or "대화" in all_text or "챗" in all_text:
        entities.append({
            "entity_id": "ENT-005",
            "entity_name": "CHAT_SESSION",
            "entity_description": "AI 상담 및 대화 세션 정보를 관리하는 엔티티",
            "columns": [
                col("SESSION_ID", "세션ID", "VARCHAR", "50", pk="Y", constraint="대화 세션 고유 식별자"),
                col("USER_ID", "사용자ID", "VARCHAR", "50", fk="Y", constraint="사용자 참조"),
                col("MODEL_ID", "모델ID", "VARCHAR", "50", fk="Y", constraint="AI 모델 참조"),
                col("CHANNEL_CODE", "채널코드", "VARCHAR", "30", constraint="웹/모바일/내부업무 채널"),
                col("SESSION_STATUS_CODE", "세션상태코드", "VARCHAR", "20", constraint="진행/종료 상태 코드"),
                col("STARTED_AT", "시작일시", "DATETIME", "", constraint="세션 시작 일시"),
                col("ENDED_AT", "종료일시", "DATETIME", "", not_null="", constraint="세션 종료 일시"),
            ],
        })

    if "로그" in all_text or "감사" in all_text or "이력" in all_text:
        entities.append({
            "entity_id": "ENT-006",
            "entity_name": "AUDIT_LOG",
            "entity_description": "사용자 행위와 시스템 처리 이력을 관리하는 엔티티",
            "columns": [
                col("LOG_ID", "로그ID", "VARCHAR", "50", pk="Y", constraint="로그 고유 식별자"),
                col("USER_ID", "사용자ID", "VARCHAR", "50", fk="Y", not_null="", constraint="사용자 참조"),
                col("ACTION_CODE", "행위코드", "VARCHAR", "50", constraint="접근/조회/변경 등 행위 코드"),
                col("TARGET_RESOURCE", "대상자원", "VARCHAR", "200", constraint="처리 대상 자원"),
                col("RESULT_CODE", "결과코드", "VARCHAR", "20", constraint="성공/실패 결과 코드"),
                col("LOGGED_AT", "기록일시", "DATETIME", "", constraint="로그 기록 일시"),
            ],
        })

    if not entities:
        entities.extend([
            {
                "entity_id": "ENT-001",
                "entity_name": "SYSTEM_REQUIREMENT",
                "entity_description": "요구사항 기반 업무 기능 정보를 관리하는 엔티티",
                "columns": [
                    col("REQUIREMENT_ID", "요구사항ID", "VARCHAR", "50", pk="Y", constraint="요구사항 고유 식별자"),
                    col("REQUIREMENT_NAME", "요구사항명", "VARCHAR", "200", constraint="요구사항 명칭"),
                    col("REQUIREMENT_TYPE_CODE", "요구사항유형코드", "VARCHAR", "30", constraint="기능/성능/보안 등 유형 코드"),
                    col("PRIORITY_CODE", "우선순위코드", "VARCHAR", "20", constraint="우선순위 코드"),
                    col("DESCRIPTION", "설명", "TEXT", "", constraint="요구사항 상세 설명"),
                    col("CREATED_AT", "생성일시", "DATETIME", "", constraint="데이터 생성 일시"),
                ],
            },
            {
                "entity_id": "ENT-002",
                "entity_name": "COMMON_CODE",
                "entity_description": "시스템 공통 코드 정보를 관리하는 엔티티",
                "columns": [
                    col("CODE_ID", "코드ID", "VARCHAR", "50", pk="Y", constraint="코드 고유 식별자"),
                    col("CODE_GROUP_ID", "코드그룹ID", "VARCHAR", "50", constraint="코드 그룹 식별자"),
                    col("CODE_NAME", "코드명", "VARCHAR", "100", constraint="코드 명칭"),
                    col("USE_YN", "사용여부", "CHAR", "1", constraint="Y/N"),
                    col("SORT_ORDER", "정렬순서", "NUMBER", "5", constraint="표시 정렬 순서"),
                ],
            },
        ])

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
    if "USER_ACCOUNT" in entity_names and "CHAT_SESSION" in entity_names:
        relationships.append({"from_entity": "USER_ACCOUNT", "to_entity": "CHAT_SESSION", "relationship": "1:N", "description": "하나의 사용자는 여러 AI 상담 세션을 생성할 수 있다."})
    if "AI_MODEL" in entity_names and "CHAT_SESSION" in entity_names:
        relationships.append({"from_entity": "AI_MODEL", "to_entity": "CHAT_SESSION", "relationship": "1:N", "description": "하나의 AI 모델은 여러 상담 세션에서 사용될 수 있다."})
    if "USER_ACCOUNT" in entity_names and "AUDIT_LOG" in entity_names:
        relationships.append({"from_entity": "USER_ACCOUNT", "to_entity": "AUDIT_LOG", "relationship": "1:N", "description": "하나의 사용자는 여러 감사 로그를 남길 수 있다."})

    return {
        "system_name": "통합 AI 플랫폼" if requirement.get("requirement_id") == "SYSTEM-ALL" else "CBD 자금이체 시스템",
        "stage_name": "설계",
        "created_date": str(date.today()),
        "version": "v1.0",
        "erd_id": "ERD-" + requirement.get("requirement_id", "REQ-001"),
        "erd_name": requirement.get("requirement_name", "요구사항")
        if requirement.get("requirement_id") == "SYSTEM-ALL"
        else requirement.get("requirement_name", "요구사항") + " ERD",
        "requirement_id": requirement.get("requirement_id", ""),
        "requirement_name": requirement.get("requirement_name", ""),
        "entities": entities,
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

    integrated_requirement = build_integrated_requirement(requirement_doc)
    erd = generate_erd_json_from_requirement(integrated_requirement, use_llm=use_llm)

    Path("./json_temp").mkdir(exist_ok=True)
    with open("./json_temp/erd_agent_output.json", "w", encoding="utf-8") as f:
        json.dump(erd, f, ensure_ascii=False, indent=2)

    return erd


if __name__ == "__main__":
    generate_erd_json(use_llm=True)
    print("[완료] ERD JSON: ./json_temp/erd_agent_output.json")
