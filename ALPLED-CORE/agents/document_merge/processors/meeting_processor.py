# 회의록의 요약과 요구사항 추가, 수정, 삭제 내용을 분석합니다.

import json
from typing import Any

from agents.document_merge.processors.artifact_parser import parse_artifact
from tools.llm.llm_client import LLMClient
from tools.llm.response_parser import parse_json_response


def analyze_meetings(
    file_paths: list[str],
    *,
    llm_client: LLMClient | None = None,
    docs_cd: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    texts: list[tuple[str, str]] = []
    warnings: list[dict[str, Any]] = []
    for path in file_paths:
        parsed = parse_artifact(path)
        if parsed["success"]:
            data = parsed["data"]
            texts.append((path, _meeting_text(data)))
        else:
            warnings.append({"code": "MEETING_PARSE_FAILED", "message": parsed["error"]["message"], "file_path": path})

    if not texts:
        return [], warnings
    if llm_client is not None:
        system_prompt = "회의록을 ADD, UPDATE, DELETE 변경 항목 JSON 배열로 분류하세요."
        normalized_docs_cd = str(docs_cd or "").upper()
        if normalized_docs_cd == "ERD":
            system_prompt = (
                "회의록의 데이터 구조 변경사항을 JSON으로 추출하세요. "
                "최상위 형식은 {\"meeting_change_items\":[...]}이며 각 항목은 "
                "change_id, change_type(ADD|UPDATE|DELETE), title, content, "
                "required_entities, required_columns, required_relationships를 포함합니다. "
                "required_columns는 [{\"entity\":\"논리 엔티티명 또는 tbl_ 물리명\","
                "\"columns\":[{\"name\":\"논리 속성명\",\"column\":\"snake_case 물리명\","
                "\"data_type\":\"타입\",\"nullable\":true}]}] 형식입니다. "
                "required_relationships는 [{\"from\":\"부모 엔티티\","
                "\"to\":\"자식 엔티티\",\"type\":\"1:N|N:M|1:1\","
                "\"via\":\"N:M 교차 엔티티 또는 null\"}] 형식입니다. "
                "회의록에 근거가 없는 엔티티, 컬럼, 관계는 만들지 마세요."
            )
        elif normalized_docs_cd == "DB":
            system_prompt = (
                "DB 설계서 수정 회의록에서 DB 명세 변경사항을 JSON으로 추출하세요. "
                "최상위 형식은 반드시 {\"meeting_change_items\":[...]}입니다. "
                "각 항목은 change_id, change_type(ADD|UPDATE|DELETE), title, content, "
                "target_table, target_column, db_change_type, data_type, length, nullable, "
                "default, constraints, indexes를 포함하세요. "
                "db_change_type은 TABLE_ADD|TABLE_UPDATE|TABLE_DELETE|COLUMN_ADD|"
                "COLUMN_UPDATE|COLUMN_DELETE|COLUMN_TYPE_CHANGE|COLUMN_LENGTH_CHANGE|"
                "NULLABLE_CHANGE|DEFAULT_CHANGE|CONSTRAINT_CHANGE|INDEX_CHANGE 중 하나로 분류하세요. "
                "테이블명, 컬럼명, 데이터 타입, 길이, PK/FK/INDEX, NOT NULL, DEFAULT, "
                "제약조건 변경을 누락하지 마세요. "
                "회의록에 명시되지 않은 테이블/컬럼/제약조건은 추측하지 마세요. "
                "변경사항이 명시되어 있으면 빈 배열을 반환하지 말고 최소 1개 이상의 "
                "meeting_change_items를 반환하세요."
            )
        llm_result = llm_client.chat(
            [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": json.dumps([{"source_path": path, "text": text} for path, text in texts], ensure_ascii=False),
                },
            ]
        )
        if llm_result["success"]:
            parsed_response = parse_json_response(llm_result["data"])
            if parsed_response["success"]:
                value = parsed_response["data"]
                if isinstance(value, dict):
                    value = value.get("meeting_change_items", value.get("changes", []))
                if isinstance(value, list):
                    if value:
                        return value, warnings
                    warnings.append(
                        {
                            "code": "MEETING_LLM_EMPTY_RESULT",
                            "message": "회의록 LLM 분석 결과가 빈 배열이어서 원문 기반 fallback을 사용합니다.",
                        }
                    )
                    return _fallback_changes(texts, docs_cd), warnings
        warnings.append({"code": "MEETING_LLM_FALLBACK", "message": "회의록 LLM 분석에 실패하여 룰 기반 결과를 사용합니다."})

    return _fallback_changes(texts, docs_cd), warnings


def _fallback_changes(
    texts: list[tuple[str, str]],
    docs_cd: str | None,
) -> list[dict[str, Any]]:
    normalized_docs_cd = str(docs_cd or "").upper()
    return [
        {
            "change_id": f"MEETING-FALLBACK-{index:03d}",
            "change_type": "UPDATE",
            "title": f"{normalized_docs_cd or '문서'} 회의록 변경사항",
            "source_path": path,
            "target_id": None,
            "content": text,
        }
        for index, (path, text) in enumerate(texts, start=1)
    ]


def _meeting_text(data: dict[str, Any]) -> str:
    parts: list[str] = []
    text = str(data.get("text") or "").strip()
    if text:
        parts.append(text)

    tables = data.get("tables")
    if isinstance(tables, list):
        table_lines: list[str] = []
        for table_index, table in enumerate(tables, start=1):
            if not isinstance(table, list):
                continue
            rows = []
            for row in table:
                if not isinstance(row, list):
                    continue
                cells = [str(cell).strip() for cell in row if str(cell).strip()]
                if cells:
                    rows.append(" | ".join(cells))
            if rows:
                table_lines.append(f"[표 {table_index}]\n" + "\n".join(rows))
        if table_lines:
            parts.append("\n\n".join(table_lines))

    if parts:
        return "\n\n".join(parts)
    return str(json.dumps(data.get("raw_json", data), ensure_ascii=False))
