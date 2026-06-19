# 아키텍처 컴포넌트 간의 관계를 생성합니다.

from typing import Any


DEFAULT_FLOW = [
    ("WEB", "API", "HTTP/API 요청"),
    ("API", "WORKFLOW", "산출물 생성 요청"),
    ("WORKFLOW", "LLM", "LLM/Vision 추론 요청"),
    ("WORKFLOW", "VECTOR_DB", "RAG 검색"),
    ("API", "RDBMS", "메타데이터 조회 및 저장"),
    ("API", "FILE_STORAGE", "파일 업로드 및 다운로드"),
    ("WORKFLOW", "FILE_STORAGE", "입력/출력 파일 처리"),
    ("API", "EXTERNAL", "외부 시스템 연계"),
]


def build_component_relations(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    component_ids = {component["component_id"] for component in components}
    relations = [
        {
            "relation_id": f"REL-{len(relations) + 1:03d}" if False else "",
            "source": source,
            "target": target,
            "description": description,
            "protocol": "HTTPS" if source in {"WEB", "API"} else "Internal API",
        }
        for source, target, description in DEFAULT_FLOW
        if source in component_ids and target in component_ids
    ]
    if not relations and len(components) >= 2:
        relations = [
            {
                "source": components[index]["component_id"],
                "target": components[index + 1]["component_id"],
                "description": "컴포넌트 간 처리 흐름",
                "protocol": "Internal API",
            }
            for index in range(len(components) - 1)
        ]
    return normalize_relations(relations, components)


def normalize_relations(
    items: list[Any],
    components: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    component_ids = {component["component_id"] for component in components}
    relations: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        source = _component_id(item.get("source") or item.get("from"))
        target = _component_id(item.get("target") or item.get("to"))
        if source not in component_ids or target not in component_ids or source == target:
            continue
        key = (source, target)
        if key in seen:
            continue
        seen.add(key)
        relations.append(
            {
                **item,
                "relation_id": str(item.get("relation_id") or f"REL-{len(relations) + 1:03d}"),
                "source": source,
                "target": target,
                "description": str(item.get("description") or item.get("label") or "컴포넌트 간 연동"),
                "protocol": str(item.get("protocol") or "Internal API"),
            }
        )
    return relations


def _component_id(value: Any) -> str:
    return "".join(char if char.isalnum() else "_" for char in str(value or "").upper()).strip("_")
