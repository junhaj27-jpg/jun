# 아키텍처 컴포넌트 간의 관계를 생성합니다.
#
# mid_stack에 들어온 실제 기술명은 주로 component name에 반영되고,
# relation에서는 protocol을 보강합니다. 예: SQLAlchemy, S3, Redis, Qdrant 등.

from __future__ import annotations

from typing import Any


ENTRY_LAYERS = {"External Actor", "Presentation Layer"}
APPLICATION_LAYERS = {"Application Layer"}
ORCHESTRATION_LAYERS = {"Agent Orchestration Layer"}
AI_LAYERS = {"AI/LLM Layer"}
DATA_LAYERS = {"Data Layer"}
EXTERNAL_LAYERS = {"External Integration Layer"}
OPERATION_LAYERS = {"Operation Layer"}


def build_component_relations(
    components: list[dict[str, Any]],
    architecture_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """컴포넌트 관계 fallback을 생성합니다.

    LLM이 실패해도 사용자 입력 기반 Mermaid가 깨지지 않도록, 고정 WEB→API→WORKFLOW 체인 대신
    계층/역할 기반 허브-스포크 구조를 만듭니다.
    """
    architecture_config = architecture_config or {}
    normalized_components = [c for c in components if isinstance(c, dict) and c.get("component_id")]
    if len(normalized_components) < 2:
        return []

    by_layer = _group_by_layer(normalized_components)
    relations: list[dict[str, Any]] = []

    entry = _first(by_layer, ["External Actor", "Presentation Layer"])
    presentation = _first(by_layer, ["Presentation Layer"])
    app_hub = _first(by_layer, ["Application Layer"])
    workflow_hub = _first(by_layer, ["Agent Orchestration Layer"])
    ai_hub = _first(by_layer, ["AI/LLM Layer"])

    # 사용자/프레젠테이션 → API/업무 서비스
    if entry and app_hub and entry["component_id"] != app_hub["component_id"]:
        relations.append(_rel(entry, app_hub, "사용자 요청 전달", _external_protocol(architecture_config)))
    elif presentation and app_hub and presentation["component_id"] != app_hub["component_id"]:
        relations.append(_rel(presentation, app_hub, "업무 API 요청 전달", _external_protocol(architecture_config)))

    # API/업무 서비스 → 인증/업무 하위서비스, 워크플로우, AI, 저장소, 외부연계, 운영
    if app_hub:
        for target in _without_first(by_layer.get("Application Layer", [])):
            if _looks_like(target, ["auth", "인증", "sso", "oauth", "jwt", "api key"]):
                relations.append(_rel(app_hub, target, "인증 및 권한 검증 요청", _auth_protocol(architecture_config)))
            else:
                relations.append(_rel(app_hub, target, "내부 업무 기능 호출", "Internal API"))
        for target in by_layer.get("Agent Orchestration Layer", []):
            relations.append(_rel(app_hub, target, "업무 처리 및 산출물 생성 요청", _internal_protocol(architecture_config)))
        for target in by_layer.get("AI/LLM Layer", []):
            # 워크플로우가 있으면 AI 호출은 workflow에서 보내는 것이 더 자연스럽다.
            if not workflow_hub:
                relations.append(_rel(app_hub, target, "AI 처리 요청", _internal_protocol(architecture_config)))
        for target in by_layer.get("Data Layer", []):
            relations.append(_rel(app_hub, target, _data_description(target, workflow=False), _data_protocol(target, architecture_config)))
        for target in by_layer.get("External Integration Layer", []):
            relations.append(_rel(app_hub, target, "외부 시스템 연계", "HTTPS/API"))
        for target in by_layer.get("Operation Layer", []):
            relations.append(_rel(app_hub, target, "업무 처리 로그 및 상태 수집", _operation_protocol(target, architecture_config)))

    # 워크플로우 → AI, 저장소, 큐/운영
    for source in by_layer.get("Agent Orchestration Layer", []):
        for target in by_layer.get("AI/LLM Layer", []):
            relations.append(_rel(source, target, "AI 추론 또는 RAG 처리 요청", _internal_protocol(architecture_config)))
        for target in by_layer.get("Data Layer", []):
            relations.append(_rel(source, target, _data_description(target, workflow=True), _data_protocol(target, architecture_config)))
        for target in by_layer.get("Operation Layer", []):
            relations.append(_rel(source, target, "작업 실행 로그 및 장애 이벤트 수집", _operation_protocol(target, architecture_config)))

    # AI/LLM → Vector DB 등 AI 저장소
    if ai_hub:
        for target in by_layer.get("Data Layer", []):
            if _looks_like(target, ["vector", "벡터", "embedding", "임베딩", "qdrant", "milvus", "weaviate"]):
                relations.append(_rel(ai_hub, target, "임베딩 검색 및 문서 컨텍스트 조회", _data_protocol(target, architecture_config)))

    # 관계가 너무 적으면 계층 순서에 따라 최소 연결만 보강한다.
    if not relations:
        relations = _minimal_layer_relations(normalized_components, architecture_config)

    return normalize_relations(relations, normalized_components)


def normalize_relations(
    items: list[Any],
    components: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    component_ids = {component["component_id"] for component in components if isinstance(component, dict) and component.get("component_id")}
    relations: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        source = _component_id(item.get("source") or item.get("from"))
        target = _component_id(item.get("target") or item.get("to"))
        if source not in component_ids or target not in component_ids or source == target:
            continue
        description = str(item.get("description") or item.get("label") or "컴포넌트 간 연동")
        key = (source, target, description)
        if key in seen:
            continue
        seen.add(key)
        relations.append(
            {
                **item,
                "relation_id": str(item.get("relation_id") or f"REL-{len(relations) + 1:03d}"),
                "source": source,
                "target": target,
                "description": description,
                "protocol": str(item.get("protocol") or "Internal API"),
            }
        )
    return relations


def _group_by_layer(components: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for component in components:
        grouped.setdefault(str(component.get("layer") or "Application Layer"), []).append(component)
    return grouped


def _first(grouped: dict[str, list[dict[str, Any]]], layers: list[str]) -> dict[str, Any] | None:
    for layer in layers:
        values = grouped.get(layer) or []
        if values:
            return values[0]
    return None


def _without_first(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return items[1:] if len(items) > 1 else []


def _rel(source: dict[str, Any], target: dict[str, Any], description: str, protocol: str) -> dict[str, Any]:
    return {
        "source": source["component_id"],
        "target": target["component_id"],
        "description": description,
        "protocol": protocol,
    }


def _external_protocol(config: dict[str, Any]) -> str:
    text = _config_text(config)
    if "https" in text:
        return "HTTPS"
    if "api key" in text or "api" in text:
        return "HTTPS/API"
    return "HTTPS"


def _internal_protocol(config: dict[str, Any]) -> str:
    text = _config_text(config)
    if "grpc" in text:
        return "gRPC"
    return "Internal API"


def _auth_protocol(config: dict[str, Any]) -> str:
    text = _config_text(config)
    if "oauth" in text:
        return "OAuth2"
    if "jwt" in text:
        return "JWT"
    if "api key" in text or "api-key" in text:
        return "API Key"
    if "sso" in text:
        return "SSO"
    return "Auth API"



def _data_description(component: dict[str, Any], workflow: bool = False) -> str:
    text = f"{component.get('component_id', '')} {component.get('name', '')} {component.get('description', '')}".lower()
    if any(word in text for word in ["s3", "bucket", "object", "오브젝트", "파일", "storage", "스토리지", "nas", "minio"]):
        return "생성 산출물 및 업로드 파일 저장" if workflow else "파일 업로드/다운로드 및 산출물 파일 저장"
    if any(word in text for word in ["redis", "cache", "캐시", "session", "세션"]):
        return "작업 실행 상태 캐시 저장" if workflow else "세션 및 캐시 데이터 저장/조회"
    if any(word in text for word in ["vector", "벡터", "qdrant", "milvus", "weaviate", "embedding", "임베딩"]):
        return "임베딩 및 검색 컨텍스트 저장/조회" if workflow else "검색 인덱스 및 임베딩 데이터 조회"
    if any(word in text for word in ["search", "검색", "opensearch", "elasticsearch", "solr"]):
        return "검색 인덱스 갱신 및 조회"
    return "작업 상태 및 산출물 메타데이터 저장" if workflow else "업무 데이터 및 메타데이터 저장/조회"

def _data_protocol(component: dict[str, Any], config: dict[str, Any] | None = None) -> str:
    config = config or {}
    component_text = f"{component.get('component_id', '')} {component.get('name', '')} {component.get('description', '')}".lower()
    config_text = _config_text(config)

    # 저장소 유형 판단은 component 자체의 이름/설명 기준으로 먼저 판단합니다.
    # config 전체에 S3가 있다고 해서 MySQL RDS까지 S3 API가 되면 안 됩니다.
    if any(word in component_text for word in ["s3", "bucket"]):
        return "S3 API"
    if any(word in component_text for word in ["minio", "object", "오브젝트", "파일", "storage"]):
        return "Object Storage API"
    if any(word in component_text for word in ["redis", "cache", "캐시", "session"]):
        return "Redis Protocol"
    if any(word in component_text for word in ["qdrant", "milvus", "weaviate", "vector", "벡터"]):
        return "Vector API"
    if any(word in component_text for word in ["mysql", "oracle", "postgres", "mariadb", "rdb", "dbms", "database"]):
        if "sqlalchemy" in config_text or "sqlalchemy" in component_text:
            return "SQLAlchemy/SQL"
        return "SQL/JDBC"
    return "Internal API"


def _operation_protocol(component: dict[str, Any], config: dict[str, Any] | None = None) -> str:
    text = f"{component.get('component_id', '')} {component.get('name', '')} {component.get('description', '')} {_config_text(config or {})}".lower()
    if any(word in text for word in ["prometheus", "grafana"]):
        return "Metrics/HTTP"
    if any(word in text for word in ["elk", "opensearch", "elasticsearch"]):
        return "Log/Event"
    if "opentelemetry" in text:
        return "OpenTelemetry"
    return "Log/Event"


def _looks_like(component: dict[str, Any], needles: list[str]) -> bool:
    text = f"{component.get('component_id', '')} {component.get('name', '')} {component.get('description', '')}".lower()
    return any(needle.lower() in text for needle in needles)


def _minimal_layer_relations(components: list[dict[str, Any]], config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    order = {
        "External Actor": 0,
        "Presentation Layer": 1,
        "Application Layer": 2,
        "Agent Orchestration Layer": 3,
        "AI/LLM Layer": 4,
        "Data Layer": 5,
        "External Integration Layer": 6,
        "Operation Layer": 7,
    }
    sorted_components = sorted(components, key=lambda c: order.get(str(c.get("layer")), 50))
    relations = []
    for index in range(len(sorted_components) - 1):
        source = sorted_components[index]
        target = sorted_components[index + 1]
        if str(source.get("layer")) in DATA_LAYERS | OPERATION_LAYERS:
            continue
        relations.append(_rel(source, target, "컴포넌트 간 처리 흐름", _internal_protocol(config or {})))
    return relations


def _config_text(config: dict[str, Any]) -> str:
    return f"{config.get('middleware_stack', '')} {config.get('mid_stack', '')} {config.get('firewall_setting', '')} {config.get('fwl_settings', '')} {config.get('auth_method', '')} {config.get('hardware_spec', '')} {config.get('hard_spec', '')}".lower()


def _component_id(value: Any) -> str:
    normalized = "".join(char if char.isalnum() else "_" for char in str(value or "").upper()).strip("_")
    if normalized and normalized[0].isdigit():
        normalized = "COMP_" + normalized
    return normalized
