# 문서 코드별 최종 문서 JSON 구조를 정의합니다.

from copy import deepcopy
from typing import Any


REDUCE_HARNESS: dict[str, dict[str, Any]] = {
    "SRS": {"docs_cd": "SRS", "requirement_json_list": []},
    "INTERFACE": {"docs_cd": "INTERFACE", "interface_json_list": [], "ui_structure": []},
    "TS": {"docs_cd": "TS", "integrated_test_scenario_json": {}},
    "ERD": {"docs_cd": "ERD", "erd_entity_json": {}, "mermaid_image_path": ""},
    "DB": {"docs_cd": "DB", "db_design_json": {}},
    "ARCH": {
        "docs_cd": "ARCH",
        "architecture_document_json": {},
        "mermaid_image_path": "",
    },
}


def get_empty_document_json(docs_cd: str) -> dict[str, Any]:
    try:
        return deepcopy(REDUCE_HARNESS[docs_cd])
    except KeyError as exc:
        raise ValueError(f"지원하지 않는 docs_cd입니다: {docs_cd}") from exc
