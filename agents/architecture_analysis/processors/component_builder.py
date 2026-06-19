# 요구사항을 기반으로 아키텍처 컴포넌트 후보를 생성합니다.

from typing import Any


NON_FUNCTIONAL_TYPES = {
    "보안",
    "보안 요구사항",
    "성능",
    "성능 요구사항",
    "품질",
    "품질 요구사항",
    "운영",
    "운영 요구사항",
    "연계",
    "연계 요구사항",
    "인터페이스",
    "인터페이스 요구사항",
    "인프라",
    "제약사항",
    "데이터",
    "데이터 요구사항",
}


def build_architecture_rag_queries(
    requirements: list[dict[str, Any]],
    project_sn: int | None,
) -> list[dict[str, Any]]:
    categories = [
        ("security", "보안 요구사항 접근 제어 인증 암호화"),
        ("performance", "성능 요구사항 응답시간 처리량 확장성"),
        ("quality", "품질 요구사항 가용성 안정성 유지보수성"),
        ("operation", "운영 요구사항 모니터링 로그 백업 복구"),
        ("integration", "연계 요구사항 외부 API 인터페이스"),
        ("deployment", "배포 환경 요구사항 서버 구성 클라우드 네트워크"),
        ("data", "데이터 보관 백업 개인정보 파일 저장소"),
    ]
    requirement_types = sorted(
        {
            str(item.get("requirement_type") or item.get("type") or "")
            for item in requirements
            if isinstance(item, dict)
        }
    )
    return [
        {
            "search_intent": f"아키텍처 {category} 비기능 요구사항 검색",
            "query": query,
            "filters": {
                "project_sn": project_sn,
                "requirement_type": [
                    item for item in requirement_types if item and item not in {"기능", "기능 요구사항"}
                ]
                or list(NON_FUNCTIONAL_TYPES),
            },
        }
        for category, query in categories
    ]


def filter_architecture_requirements(items: list[Any]) -> list[dict[str, Any]]:
    return [item for item in items if isinstance(item, dict)]


def build_architecture_drivers(
    requirements: list[dict[str, Any]],
    architecture_config: dict[str, Any],
    rag_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    text = f"{requirements} {architecture_config} {rag_results}".lower()
    drivers = [
        ("security", "보안 Driver", "인증, 접근 제어, 암호화 등 보안 요구사항을 아키텍처에 반영합니다."),
        ("performance", "성능 Driver", "응답시간, 처리량, 확장성 요구사항을 반영합니다."),
        ("operation", "운영 Driver", "모니터링, 로그, 백업, 장애 복구 요구사항을 반영합니다."),
        ("integration", "연계 Driver", "외부 시스템 및 API 연계 구조를 반영합니다."),
        ("deployment", "배포 Driver", "배포 환경, 서버 구성, 네트워크 구성을 반영합니다."),
        ("data", "데이터 관리 Driver", "DB, 파일 저장소, Vector DB, 데이터 보관 정책을 반영합니다."),
    ]
    return [
        {"driver_id": f"DRV-{index + 1:03d}", "category": category, "name": name, "description": description}
        for index, (category, name, description) in enumerate(drivers)
        if _has_category(text, category) or category in {"security", "performance", "operation", "integration", "deployment", "data"}
    ]


def build_component_candidates(
    requirements: list[dict[str, Any]],
    architecture_config: dict[str, Any],
    drivers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    base = [
        ("WEB", "Web Client", "Presentation Layer", "사용자가 접근하는 웹 클라이언트입니다."),
        ("API", "API Server", "Application Layer", "FastAPI 기반 API 및 인증/인가 처리를 담당합니다."),
        ("WORKFLOW", "Agent Workflow Server", "Agent Orchestration Layer", "LangGraph 기반 생성 Workflow와 Supervisor 실행을 담당합니다."),
        ("LLM", "LLM Inference Server", "AI/LLM Layer", "LLM 및 Vision LLM 추론을 담당합니다."),
        ("VECTOR_DB", "Vector DB", "AI/LLM Layer", "RAG 검색용 임베딩 저장소입니다."),
        ("RDBMS", "RDBMS", "Data Layer", "프로젝트, 산출물, 파일 메타데이터를 저장합니다."),
        ("FILE_STORAGE", "File Storage", "Data Layer", "입력 파일과 생성 산출물을 저장합니다."),
    ]
    config_text = str(architecture_config).lower()
    req_text = str(requirements).lower()
    if "external" in config_text or "외부" in config_text or "api" in req_text or "연계" in req_text:
        base.append(("EXTERNAL", "External System", "External Integration Layer", "외부 연계 시스템입니다."))
    return [
        {
            "component_id": component_id,
            "name": name,
            "layer": layer,
            "description": description,
            "driver_categories": [driver["category"] for driver in drivers],
        }
        for component_id, name, layer, description in base
    ]


def normalize_components(items: list[Any]) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        component_id = str(item.get("component_id") or item.get("id") or item.get("name") or f"COMP-{index + 1:03d}")
        component_id = _safe_id(component_id)
        if component_id in seen:
            continue
        seen.add(component_id)
        components.append(
            {
                **item,
                "component_id": component_id,
                "name": str(item.get("name") or item.get("component_name") or component_id),
                "layer": str(item.get("layer") or "Application Layer"),
                "description": str(item.get("description") or item.get("role") or ""),
            }
        )
    return components


def apply_architecture_changes(
    components: list[dict[str, Any]],
    changes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    updated = [dict(component) for component in components]
    by_id = {component["component_id"]: component for component in updated}
    for change in changes:
        if not isinstance(change, dict):
            continue
        operation = str(change.get("change_type") or change.get("operation") or "").upper()
        target = change.get("item") if isinstance(change.get("item"), dict) else change
        name = str(target.get("component_name") or target.get("name") or target.get("target") or "").strip()
        if not name:
            continue
        component_id = _safe_id(str(target.get("component_id") or name))
        if operation in {"DELETE", "REMOVE"}:
            updated = [component for component in updated if component["component_id"] != component_id]
            by_id.pop(component_id, None)
            continue
        if component_id not in by_id:
            component = {
                "component_id": component_id,
                "name": name,
                "layer": str(target.get("layer") or "Application Layer"),
                "description": str(target.get("description") or change.get("description") or "회의록 변경사항으로 추가된 컴포넌트입니다."),
            }
            updated.append(component)
            by_id[component_id] = component
        else:
            by_id[component_id]["description"] = str(change.get("description") or by_id[component_id].get("description") or "")
    return normalize_components(updated)


def _has_category(text: str, category: str) -> bool:
    aliases = {
        "security": ("security", "보안", "인증", "권한"),
        "performance": ("performance", "성능", "응답", "처리량"),
        "operation": ("operation", "운영", "모니터링", "백업"),
        "integration": ("integration", "연계", "interface", "api"),
        "deployment": ("deployment", "배포", "서버", "cloud"),
        "data": ("data", "데이터", "db", "file", "vector"),
    }
    return any(alias in text for alias in aliases[category])


def _safe_id(value: str) -> str:
    normalized = "".join(char if char.isalnum() else "_" for char in value.upper()).strip("_")
    return normalized or "COMP"
