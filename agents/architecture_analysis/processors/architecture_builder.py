# 아키텍처 구조와 문서 JSON을 생성합니다.

from collections import defaultdict
from typing import Any


def build_layers(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for component in components:
        grouped[str(component.get("layer") or "Application Layer")].append(component["component_id"])
    preferred = [
        "Presentation Layer",
        "Application Layer",
        "Agent Orchestration Layer",
        "AI/LLM Layer",
        "Data Layer",
        "External Integration Layer",
    ]
    layer_names = [name for name in preferred if name in grouped] + [
        name for name in grouped if name not in preferred
    ]
    return [
        {
            "layer_id": f"LAYER-{index + 1:03d}",
            "name": name,
            "component_ids": grouped[name],
        }
        for index, name in enumerate(layer_names)
    ]


def build_deployment_environment(architecture_config: dict[str, Any]) -> dict[str, Any]:
    return {
        "environment": architecture_config.get("deployment_environment")
        or architecture_config.get("environment")
        or "운영/검증 분리 환경",
        "web_was": architecture_config.get("web_was") or architecture_config.get("server 구성") or "WEB/WAS 분리 또는 논리 분리",
        "dbms": architecture_config.get("dbms") or architecture_config.get("DBMS") or "RDBMS",
        "storage": architecture_config.get("file_storage") or architecture_config.get("storage") or "S3 또는 파일 저장소",
        "vector_db": architecture_config.get("vector_db") or "Qdrant",
        "llm_server": architecture_config.get("llm_server") or "LLM Inference Server",
    }


def build_architecture_structure(
    *,
    components: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    layers: list[dict[str, Any]],
    deployment_environment: dict[str, Any],
    drivers: list[dict[str, Any]],
    architecture_config: dict[str, Any],
) -> dict[str, Any]:
    return {
        "overview": "요구사항, 비기능 요구사항, 아키텍처 설정을 기반으로 구성한 ALPLED 아키텍처 구조입니다.",
        "components": components,
        "relations": relations,
        "edges": relations,
        "layers": layers,
        "subgraphs": layers,
        "deployment_environment": deployment_environment,
        "drivers": drivers,
        "security": "인증, 권한, 데이터 보호, 접근 제어를 반영합니다.",
        "performance": "응답시간, 병렬 처리, 확장성을 고려합니다.",
        "operation": "로그, 모니터링, 백업, 장애 대응을 고려합니다.",
        "integration": "외부 시스템 및 API 연계 구조를 고려합니다.",
        "deployment": "서버 구성과 배포 환경을 고려합니다.",
        "architecture_config": architecture_config,
        "architecture_config_reflected": bool(architecture_config),
    }


def build_architecture_document(
    *,
    structure: dict[str, Any],
    rag_results: list[dict[str, Any]],
    meeting_change_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    requirement_implementations = build_requirement_implementations(
        structure=structure,
        rag_results=rag_results,
    )
    return {
        "overview": structure["overview"],
        "requirement_implementations": requirement_implementations,
        "components": [
            {
                "component_id": component["component_id"],
                "name": component["name"],
                "layer": component.get("layer"),
                "description": component.get("description"),
            }
            for component in structure.get("components", [])
        ],
        "relations": structure.get("relations", []),
        "layers": structure.get("layers", []),
        "deployment_environment": structure.get("deployment_environment", {}),
        "design_drivers": structure.get("drivers", []),
        "security_considerations": structure.get("security"),
        "performance_considerations": structure.get("performance"),
        "operation_considerations": structure.get("operation"),
        "integration_considerations": structure.get("integration"),
        "deployment_considerations": structure.get("deployment"),
        "rag_references": rag_results,
        "meeting_change_items": meeting_change_items or [],
        "architecture_config": structure.get("architecture_config", {}),
        "architecture_config_reflected": structure.get("architecture_config_reflected", False),
    }


def extract_existing_structure(existing: dict[str, Any]) -> dict[str, Any]:
    if isinstance(existing.get("architecture_structure_json"), dict):
        return existing["architecture_structure_json"]
    return existing


def build_requirement_implementations(
    *,
    structure: dict[str, Any],
    rag_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    drivers = structure.get("drivers") or []
    components = structure.get("components") or []
    relations = structure.get("relations") or []
    deployment_environment = structure.get("deployment_environment") or {}
    architecture_config = structure.get("architecture_config") or {}
    references_by_category = _group_rag_references_by_category(rag_results)

    items: list[dict[str, Any]] = []
    for index, driver in enumerate(drivers, start=1):
        if not isinstance(driver, dict):
            continue
        category = str(driver.get("category") or f"driver-{index}")
        references = references_by_category.get(category, [])
        target_components = _components_for_driver(category, components)
        content = _architecture_requirement_content(driver, references)
        implementation = _architecture_implementation_content(
            category=category,
            driver=driver,
            components=target_components,
            relations=relations,
            deployment_environment=deployment_environment,
            architecture_config=architecture_config,
            references=references,
        )
        items.append(
            {
                "requirement_id": "",
                "category": category,
                "requirement_name": str(driver.get("name") or category),
                "description": content,
                "implementation": implementation,
                "source_requirement_ids": _reference_ids(references),
            }
        )
    return items


def _architecture_requirement_content(
    driver: dict[str, Any],
    references: list[dict[str, Any]],
) -> str:
    name = str(driver.get("name") or "아키텍처 요구사항")
    reference_summary = _reference_summary(references)
    if reference_summary:
        return f"{name} 확보를 위해 {reference_summary}을 설계 기준으로 반영해야 함"
    description = str(driver.get("description") or "").strip()
    if description:
        return _sentence_to_requirement(description)
    return f"{name}을 시스템 아키텍처 설계 기준으로 반영해야 함"


def _architecture_implementation_content(
    *,
    category: str,
    driver: dict[str, Any],
    components: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    deployment_environment: dict[str, Any],
    architecture_config: dict[str, Any],
    references: list[dict[str, Any]],
) -> str:
    component_names = [
        str(component.get("name") or component.get("component_id"))
        for component in components
        if isinstance(component, dict)
    ]
    target_text = ", ".join(component_names[:5]) if component_names else "관련 구성요소"
    relation_text = _relation_summary(relations, components)
    environment_text = _deployment_summary(deployment_environment, architecture_config)
    reference_text = _reference_summary(references)

    category_guides = {
        "security": "인증/인가, 접근 제어, 전송/저장 데이터 암호화, 감사 로그를 API Server와 Data Layer 경계에 적용하고 망 설정에 따라 외부 연계 구간을 분리",
        "performance": "동시 요청 처리를 고려해 API Server와 Agent Workflow Server를 독립 확장 가능하게 구성하고 LLM, Vector DB 호출은 timeout과 재시도 기준을 분리",
        "quality": "장애 격리, 오류 응답 표준화, 재처리 가능한 workflow 상태 관리를 통해 서비스 품질과 신뢰성을 확보",
        "operation": "요청 추적 ID, Agent 실행 로그, 산출물 상태, 외부 연동 실패 내역을 수집하고 백업/복구 기준을 운영 절차에 반영",
        "integration": "외부 시스템 연계는 API Server 경유로 표준화하고 인증, 오류 처리, 응답 timeout, 재시도 정책을 인터페이스별로 분리",
        "deployment": "WEB/WAS, DB, LLM, Vector DB, File Storage를 역할별 계층으로 분리하고 운영/검증 환경 및 망 설정에 맞춰 배포 단위를 분리",
        "data": "RDBMS, File Storage, Vector DB별 저장 대상과 보관 기준을 분리하고 개인정보/첨부파일/임베딩 데이터에 대한 접근 제어와 백업 정책을 적용",
    }
    guide = category_guides.get(category, str(driver.get("description") or "설계 기준에 맞춰 구성요소와 연계 구조를 구체화"))

    sentences = [
        f"{target_text}를 중심으로 {guide}합니다.",
    ]
    if relation_text:
        sentences.append(f"주요 연계 흐름은 {relation_text} 기준으로 정의합니다.")
    if environment_text:
        sentences.append(f"배포 환경은 {environment_text} 기준을 적용합니다.")
    if reference_text:
        sentences.append(f"RAG로 확인한 비기능 근거인 {reference_text}을 상세 설계 검토 기준으로 사용합니다.")
    return " ".join(sentences)


def _group_rag_references_by_category(
    rag_results: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for group in rag_results:
        if not isinstance(group, dict):
            continue
        category = _category_from_text(str(group.get("search_intent") or group.get("query") or ""))
        for item in group.get("normalized_results") or []:
            if isinstance(item, dict):
                grouped[category].append(item)
    return grouped


def _category_from_text(text: str) -> str:
    lowered = text.lower()
    mapping = {
        "security": ("security", "보안", "인증", "암호화", "접근"),
        "performance": ("performance", "성능", "응답", "처리량", "확장"),
        "quality": ("quality", "품질", "가용성", "안정성", "유지보수"),
        "operation": ("operation", "운영", "모니터링", "로그", "백업", "복구"),
        "integration": ("integration", "연계", "인터페이스", "api", "외부"),
        "deployment": ("deployment", "배포", "서버", "클라우드", "네트워크", "망"),
        "data": ("data", "데이터", "보관", "개인정보", "파일", "저장소"),
    }
    for category, needles in mapping.items():
        if any(needle in lowered for needle in needles):
            return category
    return "general"


def _components_for_driver(
    category: str,
    components: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    matched = [
        component
        for component in components
        if isinstance(component, dict)
        and (
            category in component.get("driver_categories", [])
            or category in str(component).lower()
        )
    ]
    return matched or [component for component in components if isinstance(component, dict)]


def _relation_summary(
    relations: list[dict[str, Any]],
    components: list[dict[str, Any]],
) -> str:
    component_ids = {
        str(component.get("component_id"))
        for component in components
        if isinstance(component, dict) and component.get("component_id")
    }
    selected = []
    for relation in relations:
        if not isinstance(relation, dict):
            continue
        source = str(relation.get("source") or relation.get("from") or "")
        target = str(relation.get("target") or relation.get("to") or "")
        if component_ids and source not in component_ids and target not in component_ids:
            continue
        label = str(relation.get("description") or relation.get("label") or "연계")
        selected.append(f"{source} -> {target}({label})")
        if len(selected) >= 3:
            break
    return ", ".join(item for item in selected if item)


def _deployment_summary(
    deployment_environment: dict[str, Any],
    architecture_config: dict[str, Any],
) -> str:
    values = [
        deployment_environment.get("environment"),
        deployment_environment.get("web_was"),
        deployment_environment.get("dbms"),
        deployment_environment.get("storage"),
        deployment_environment.get("vector_db"),
        deployment_environment.get("llm_server"),
    ]
    networks = architecture_config.get("networks")
    if isinstance(networks, list) and networks:
        network_names = [
            str(item.get("prj_net_nm") or item.get("network_name") or "")
            for item in networks
            if isinstance(item, dict)
        ]
        if any(network_names):
            values.append("망 구성: " + ", ".join(name for name in network_names if name))
    return ", ".join(str(value) for value in values if value)


def _reference_summary(references: list[dict[str, Any]]) -> str:
    texts = []
    for item in references[:3]:
        content = str(item.get("content") or item.get("title") or "").strip()
        if content:
            texts.append(_shorten(content, 90))
    return ", ".join(texts)


def _reference_ids(references: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for item in references:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        value = (
            item.get("requirement_id")
            or item.get("req_id")
            or metadata.get("requirement_id")
            or metadata.get("req_id")
        )
        if value and str(value) not in ids:
            ids.append(str(value))
    return ids


def _sentence_to_requirement(text: str) -> str:
    normalized = text.strip().rstrip(".")
    normalized = normalized.replace("합니다", "해야 함")
    normalized = normalized.replace("반영합니다", "반영해야 함")
    normalized = normalized.replace("고려합니다", "고려해야 함")
    if normalized.endswith("해야 함"):
        return normalized
    return f"{normalized}해야 함"


def _shorten(text: str, max_length: int) -> str:
    normalized = " ".join(text.split())
    return normalized if len(normalized) <= max_length else normalized[:max_length].rstrip() + "..."
