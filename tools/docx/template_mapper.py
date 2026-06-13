"""최종 산출물 JSON을 DOCX 생성용 payload로 변환합니다."""

from copy import deepcopy
from typing import Any

from tools.result import ToolResult, error_result, success_result


DOCUMENT_CONTENT_KEYS = {
    "SRS": ("requirement_json_list",),
    "INTERFACE": ("interface_json_list",),
    "TS": ("integrated_test_scenario_json",),
    "ERD": ("erd_entity_json", "mermaid_image_path"),
    "DB": ("db_design_json",),
    "ARCH": ("architecture_document_json", "mermaid_image_path"),
}

DOCUMENT_TITLES = {
    "SRS": "요구사항 정의서",
    "INTERFACE": "인터페이스 설계서",
    "TS": "통합시험 시나리오",
    "ERD": "ERD 설계서",
    "DB": "DB 설계서",
    "ARCH": "아키텍처 설계서",
}


def map_document_to_template(
    final_document_json: dict[str, Any],
    docs_cd: str,
) -> ToolResult:
    """docs_cd별 필수 값을 확인하고 템플릿 payload를 반환합니다."""

    if docs_cd not in DOCUMENT_CONTENT_KEYS:
        return error_result("EXPORT_DOCS_CD_INVALID", f"지원하지 않는 docs_cd입니다: {docs_cd}")
    if final_document_json.get("docs_cd") not in (None, docs_cd):
        return error_result(
            "EXPORT_DOCS_CD_MISMATCH",
            "state의 docs_cd와 final_document_json.docs_cd가 일치하지 않습니다.",
        )

    missing = [
        key for key in DOCUMENT_CONTENT_KEYS[docs_cd] if key not in final_document_json
    ]
    if missing:
        return error_result(
            "EXPORT_DOCUMENT_SCHEMA_ERROR",
            f"final_document_json 필수 값이 없습니다: {', '.join(missing)}",
        )

    return success_result(
        {
            "docs_cd": docs_cd,
            "title": DOCUMENT_TITLES[docs_cd],
            "content": {
                key: deepcopy(final_document_json[key])
                for key in DOCUMENT_CONTENT_KEYS[docs_cd]
                if key != "mermaid_image_path"
            },
            "image_paths": [
                str(final_document_json["mermaid_image_path"])
            ]
            if final_document_json.get("mermaid_image_path")
            else [],
        }
    )
