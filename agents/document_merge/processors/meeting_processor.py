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
            texts.append((path, str(data.get("text") or json.dumps(data.get("raw_json", data), ensure_ascii=False))))
        else:
            warnings.append({"code": "MEETING_PARSE_FAILED", "message": parsed["error"]["message"], "file_path": path})

    if not texts:
        return [], warnings
    if llm_client is not None:
        system_prompt = "회의록을 ADD, UPDATE, DELETE 변경 항목 JSON 배열로 분류하세요."
        if str(docs_cd or "").upper() == "ERD":
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
                    return value, warnings
        warnings.append({"code": "MEETING_LLM_FALLBACK", "message": "회의록 LLM 분석에 실패하여 룰 기반 결과를 사용합니다."})

    return [
        {"change_type": "UPDATE", "source_path": path, "target_id": None, "content": text}
        for path, text in texts
    ], warnings
