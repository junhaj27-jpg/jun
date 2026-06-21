# 아키텍처 구조와 문서 JSON을 생성합니다.

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from agents.architecture_analysis.processors.diagram_builder import build_clean_architecture_mermaid_source


LAYER_ORDER = [
    "External Actor",
    "Presentation Layer",
    "Application Layer",
    "Agent Orchestration Layer",
    "AI/LLM Layer",
    "Data Layer",
    "External Integration Layer",
    "Operation Layer",
]


CATEGORY_LABELS = {
    "security": "보안",
    "performance": "성능",
    "quality": "품질",
    "operation": "운영",
    "integration": "연계",
    "deployment": "배포",
    "data": "데이터 관리",
    "general": "공통",
}


CATEGORY_REQUIREMENT_TEXT = {
    "security": (
        "인증, 접근통제, 로그 관리, 데이터 보호 요구사항을 수용할 수 있도록 "
        "서비스 경계와 데이터 계층 경계를 분리한 보안 아키텍처를 설계해야 함"
    ),
    "performance": (
        "동시 요청, 처리량, 확장성 요구사항을 수용할 수 있도록 "
        "업무 처리와 저장소 접근을 분리한 성능 아키텍처를 설계해야 함"
    ),
    "quality": (
        "가용성, 안정성, 유지보수성 요구사항을 수용할 수 있도록 "
        "장애 격리와 오류 대응이 가능한 품질 중심 아키텍처를 설계해야 함"
    ),
    "operation": (
        "로그, 모니터링, 장애 대응, 백업 및 복구 요구사항을 수용할 수 있도록 "
        "운영 관점의 추적성과 관리성을 확보한 아키텍처를 설계해야 함"
    ),
    "integration": (
        "내부·외부 시스템 연계 요구사항을 수용할 수 있도록 "
        "표준 인터페이스, 인증, 오류 처리 기준을 포함한 연계 아키텍처를 설계해야 함"
    ),
    "deployment": (
        "업무망, 서버 구성, 저장소, 배포 환경 요구사항을 수용할 수 있도록 "
        "역할별 배포 단위와 망 구성을 분리한 배포 아키텍처를 설계해야 함"
    ),
    "data": (
        "DB, 파일 저장소, 벡터 저장소 등 데이터 관리 요구사항을 수용할 수 있도록 "
        "저장 대상, 접근 권한, 백업 기준을 분리한 데이터 아키텍처를 설계해야 함"
    ),
    "general": (
        "요구사항 생성본과 사용자 아키텍처 설정을 기준으로 "
        "업무 처리, 산출물 생성, 데이터 저장 흐름을 반영한 시스템 아키텍처를 설계해야 함"
    ),
}


CATEGORY_IMPLEMENTATION_GUIDES = {
    "security": (
        "인증/인가, 접근 제어, 전송 및 저장 데이터 보호, 감사 로그를 "
        "서비스 경계와 데이터 계층 경계에 적용하고 외부 연계 구간을 분리"
    ),
    "performance": (
        "동시 요청과 처리량을 고려하여 API 처리, Workflow 처리, 데이터 저장소 접근을 "
        "분리하고 주요 컴포넌트를 독립 확장 가능하게 구성"
    ),
    "quality": (
        "장애 격리, 오류 응답 표준화, 재처리 가능한 Workflow 상태 관리를 통해 "
        "서비스 품질과 신뢰성을 확보"
    ),
    "operation": (
        "요청 추적 ID, 실행 로그, 산출물 상태, 외부 연동 실패 내역을 수집하고 "
        "백업/복구 기준을 운영 절차에 반영"
    ),
    "integration": (
        "외부 시스템 연계는 업무 API 경유로 표준화하고 인증, 오류 처리, 응답 timeout, "
        "재시도 정책을 인터페이스별로 분리"
    ),
    "deployment": (
        "API 서버, Workflow 서버, 데이터 저장소, 파일 저장소를 역할별 계층으로 분리하고 "
        "운영/검증 환경 및 망 설정에 맞춰 배포 단위를 분리"
    ),
    "data": (
        "DB, 파일 저장소, Vector DB 등 저장소별 저장 대상과 보관 기준을 분리하고 "
        "개인정보, 첨부파일, 임베딩 데이터에 대한 접근 제어와 백업 정책을 적용"
    ),
    "general": (
        "요구사항 생성본과 사용자 인프라 설정을 기준으로 구성요소, 연계 구조, "
        "배포 환경을 구체화"
    ),
}


def build_layers(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[str]] = defaultdict(list)

    for component in components:
        if not isinstance(component, dict) or not component.get("component_id"):
            continue
        grouped[str(component.get("layer") or "Application Layer")].append(component["component_id"])

    layer_names = [name for name in LAYER_ORDER if name in grouped] + [
        name for name in grouped if name not in LAYER_ORDER
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
        or _cloud_environment(architecture_config)
        or "운영/검증 분리 환경",
        "network": architecture_config.get("network_name")
        or architecture_config.get("prj_net_nm")
        or "대상 업무망",
        "network_purpose": architecture_config.get("network_purpose")
        or architecture_config.get("network_description")
        or architecture_config.get("prj_net_prps")
        or "",
        "middleware_stack": architecture_config.get("middleware_stack")
        or architecture_config.get("mid_stack")
        or "",
        "web_was": architecture_config.get("web_was")
        or architecture_config.get("server 구성")
        or _infer_web_was(architecture_config)
        or "WEB/WAS 논리 분리",
        "dbms": architecture_config.get("dbms")
        or architecture_config.get("DBMS")
        or _infer_dbms(architecture_config)
        or "RDBMS",
        "storage": architecture_config.get("file_storage")
        or architecture_config.get("storage")
        or _infer_storage(architecture_config)
        or "파일 저장소",
        "auth_method": architecture_config.get("auth_method") or "",
        "firewall_setting": architecture_config.get("firewall_setting")
        or architecture_config.get("fwl_settings")
        or "",
        "hardware_spec": architecture_config.get("hardware_spec")
        or architecture_config.get("server_hardware_spec")
        or architecture_config.get("hard_spec")
        or "",
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
    structure = {
        "overview": "요구사항, 비기능 요구사항, 사용자 아키텍처 설정을 기반으로 구성한 시스템 아키텍처 구조입니다.",
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
    structure["architecture_description"] = build_architecture_description(structure)
    structure["architecture_mermaid"] = build_clean_architecture_mermaid_source(structure)
    return structure


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
        "architecture_description": structure.get("architecture_description")
        or build_architecture_description(structure),
        "architecture_mermaid": structure.get("architecture_mermaid")
        or build_clean_architecture_mermaid_source(structure),
        "requirement_implementations": requirement_implementations,
        "components": [
            {
                "component_id": component["component_id"],
                "name": component["name"],
                "layer": component.get("layer"),
                "description": component.get("description"),
            }
            for component in structure.get("components", [])
            if isinstance(component, dict) and component.get("component_id")
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


def build_architecture_description(structure: dict[str, Any]) -> str:
    config = structure.get("architecture_config") or {}
    components = [c for c in structure.get("components") or [] if isinstance(c, dict)]
    relations = [r for r in structure.get("relations") or [] if isinstance(r, dict)]

    network_name = _first(config.get("network_name"), config.get("prj_net_nm"), "대상 시스템")
    network_purpose = _first(
        config.get("network_purpose"),
        config.get("network_description"),
        config.get("prj_net_prps"),
    )
    middleware = _first(config.get("middleware_stack"), config.get("mid_stack"))
    firewall = _first(config.get("firewall_setting"), config.get("fwl_settings"))
    auth = _first(config.get("auth_method"))
    hardware = _first(
        config.get("hardware_spec"),
        config.get("server_hardware_spec"),
        config.get("hard_spec"),
    )
    expected = _first(config.get("expected_user_count"), config.get("expected_ccu"), config.get("expected_smtn"))
    remark = _first(config.get("remark"), config.get("rmrk"))

    sentences: list[str] = []

    if network_purpose:
        sentences.append(f"{network_name}은 {_ensure_sentence(network_purpose)}")
    else:
        sentences.append(f"{network_name}은 요구사항 기반 업무 처리와 산출물 생성을 지원하도록 구성한다.")

    if middleware:
        sentences.append(f"주요 기술 스택은 {middleware}을 기준으로 구성한다.")

    if firewall:
        sentences.append(f"통신 및 접근 제어 정책으로 {_ensure_sentence(firewall)}")

    if auth:
        sentences.append(f"인증 방식은 {auth}을 적용한다.")

    if expected:
        sentences.append(f"예상 사용자 또는 처리 규모는 {expected}을 기준으로 설계한다.")

    if hardware:
        sentences.append(f"인프라 사양은 {hardware}을 기준으로 한다.")

    if remark:
        sentences.append(f"운영 범위는 {_ensure_sentence(remark)}")

    if components:
        names = ", ".join(_component_name(c) for c in components[:8])
        sentences.append(f"주요 구성요소는 {names}로 구성된다.")

    if relations:
        sentences.append("구성요소 간 연결은 사용자 요청, 업무 처리, 산출물 생성, 데이터 저장, 외부 연계 흐름을 기준으로 정의한다.")

    return " ".join(sentence for sentence in sentences if sentence)


def build_architecture_mermaid(structure: dict[str, Any]) -> str:
    existing_mermaid = structure.get("architecture_mermaid")

    if isinstance(existing_mermaid, str) and existing_mermaid.strip():
        return existing_mermaid

    return build_clean_architecture_mermaid_source(
        structure,
        direction="LR",
        edge_label_mode="none",
        max_edges=16,
    )


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
        category = _normalize_category(category)

        references = _dedupe_references(references_by_category.get(category, []))
        target_components = _components_for_driver(category, components)

        content = _architecture_requirement_content(
            driver=driver,
            category=category,
        )

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
                "requirement_name": str(driver.get("name") or _category_label(category)),
                "description": content,
                "implementation": implementation,
                "source_requirement_ids": _reference_ids(references),
            }
        )

    return items


def _architecture_requirement_content(
    *,
    driver: dict[str, Any],
    category: str,
) -> str:
    description = _normalize_text(driver.get("description"))

    if description:
        return _sentence_to_requirement(description)

    return CATEGORY_REQUIREMENT_TEXT.get(category) or CATEGORY_REQUIREMENT_TEXT["general"]


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
        _component_name(component)
        for component in components
        if isinstance(component, dict)
    ]

    target_text = _category_target_text(category, component_names)

    guide = CATEGORY_IMPLEMENTATION_GUIDES.get(category)
    if not guide:
        guide = _normalize_text(driver.get("description")) or CATEGORY_IMPLEMENTATION_GUIDES["general"]

    sentences = [f"{target_text}를 중심으로 {guide}합니다."]

    category_hint = _category_config_hint(
        category=category,
        architecture_config=architecture_config,
        deployment_environment=deployment_environment,
    )
    if category_hint:
        sentences.append(category_hint)

    # 연계 흐름은 모든 항목에 반복하지 않고, 연계/데이터/배포 관점에서만 출력합니다.
    relation_text = _relation_summary(relations, components)
    if relation_text and category in {"integration", "data", "deployment"}:
        sentences.append(f"주요 연계 흐름은 {relation_text} 기준으로 정의합니다.")

    # 전체 배포 요약은 배포 항목에서만 출력합니다.
    if category == "deployment":
        environment_text = _deployment_summary(deployment_environment, architecture_config)
        if environment_text:
            sentences.append(f"배포 기준은 {environment_text}입니다.")

    reference_basis = _reference_basis_sentence(category, references)
    if reference_basis:
        sentences.append(reference_basis)

    return " ".join(sentence for sentence in sentences if sentence)


def _category_target_text(category: str, component_names: list[str]) -> str:
    """
    구현방안 첫 문장의 대상 컴포넌트가 매번 전체 컴포넌트로 반복되지 않도록
    카테고리별 대표 설계 대상을 잡습니다.
    """
    fallback = ", ".join(_dedupe_texts(component_names)[:3]) if component_names else "관련 구성요소"

    targets = {
        "security": "인증/인가 서비스, API 서버, 데이터 저장 계층",
        "performance": "API 서버, Workflow 처리 서버, 데이터 저장소",
        "quality": "API 서버, Workflow 처리 서버, 운영 관리 영역",
        "operation": "Workflow 처리 서버, 로그/모니터링 영역, 산출물 상태 관리 영역",
        "integration": "API 서버, 외부 연계 인터페이스, 인증 연계 구간",
        "deployment": "API 서버, Workflow 서버, DBMS, 파일 저장소",
        "data": "DBMS, 파일 저장소, Vector DB",
        "general": fallback,
    }

    return targets.get(category) or fallback


def _category_config_hint(
    *,
    category: str,
    architecture_config: dict[str, Any],
    deployment_environment: dict[str, Any],
) -> str:
    """
    사용자 입력 인프라 설정을 모든 구현방안에 똑같이 반복하지 않고,
    카테고리별로 필요한 설정만 선별해서 출력합니다.
    """
    network_name = _first(
        architecture_config.get("network_name"),
        architecture_config.get("prj_net_nm"),
        deployment_environment.get("network"),
    )
    network_purpose = _first(
        architecture_config.get("network_purpose"),
        architecture_config.get("network_description"),
        architecture_config.get("prj_net_prps"),
        deployment_environment.get("network_purpose"),
    )
    middleware = _first(
        architecture_config.get("middleware_stack"),
        architecture_config.get("mid_stack"),
        deployment_environment.get("middleware_stack"),
    )
    firewall = _first(
        architecture_config.get("firewall_setting"),
        architecture_config.get("fwl_settings"),
        deployment_environment.get("firewall_setting"),
    )
    auth = _first(
        architecture_config.get("auth_method"),
        deployment_environment.get("auth_method"),
    )
    hardware = _first(
        architecture_config.get("hardware_spec"),
        architecture_config.get("server_hardware_spec"),
        architecture_config.get("hard_spec"),
        deployment_environment.get("hardware_spec"),
    )
    expected = _first(
        architecture_config.get("expected_user_count"),
        architecture_config.get("expected_ccu"),
        architecture_config.get("expected_smtn"),
    )
    remark = _first(
        architecture_config.get("remark"),
        architecture_config.get("rmrk"),
    )
    dbms = _first(
        deployment_environment.get("dbms"),
        architecture_config.get("dbms"),
        architecture_config.get("DBMS"),
    )
    storage = _first(
        deployment_environment.get("storage"),
        architecture_config.get("file_storage"),
        architecture_config.get("storage"),
    )
    environment = _first(
        deployment_environment.get("environment"),
        architecture_config.get("deployment_environment"),
        architecture_config.get("environment"),
    )

    parts: list[str] = []

    if category == "security":
        if firewall:
            parts.append(f"망/방화벽 정책으로 {_ensure_sentence(firewall)}")
        if auth:
            parts.append(f"인증 방식은 {auth}을 적용합니다.")

    elif category == "performance":
        if expected:
            parts.append(f"예상 사용자 또는 처리 규모는 {expected}을 기준으로 산정합니다.")
        if hardware:
            parts.append(f"하드웨어 및 인프라 기준은 {hardware}입니다.")
        if middleware:
            parts.append(f"기술 스택은 {middleware}을 기준으로 성능 병목 구간을 분리합니다.")

    elif category == "quality":
        if middleware:
            parts.append(f"기술 스택은 {middleware}을 기준으로 오류 처리와 장애 격리 단위를 구분합니다.")
        if remark:
            parts.append(f"운영 담당 범위는 {_ensure_sentence(remark)}")

    elif category == "operation":
        if remark:
            parts.append(f"운영 담당 범위는 {_ensure_sentence(remark)}")
        if network_name:
            parts.append(f"{network_name} 기준으로 요청 상태, 산출물 생성 상태, 장애 이력을 추적합니다.")
        if storage:
            parts.append(f"산출물과 첨부파일은 {storage} 저장소 기준으로 보관 및 복구 정책을 적용합니다.")

    elif category == "integration":
        if auth:
            parts.append(f"연계 인증은 {auth}을 기준으로 적용합니다.")
        if network_name:
            parts.append(f"연계 구간은 {network_name}의 망 정책을 기준으로 분리합니다.")
        if firewall:
            parts.append(f"방화벽 정책은 {_ensure_sentence(firewall)}")

    elif category == "deployment":
        if network_name or environment:
            if network_name and environment:
                parts.append(f"배포 대상은 {network_name} / {environment} 기준으로 구성합니다.")
            elif network_name:
                parts.append(f"배포 대상 망은 {network_name}입니다.")
            elif environment:
                parts.append(f"배포 환경은 {environment}입니다.")
        if middleware:
            parts.append(f"기술 스택은 {middleware}을 기준으로 배포 단위를 구성합니다.")
        if hardware:
            parts.append(f"인프라 사양은 {hardware}을 기준으로 합니다.")

    elif category == "data":
        if dbms:
            parts.append(f"정형 데이터 저장소는 {dbms} 기준으로 구성합니다.")
        if storage:
            parts.append(f"파일 및 산출물 저장소는 {storage} 기준으로 구성합니다.")
        if firewall:
            parts.append(f"DB 및 저장소 접근은 {_ensure_sentence(firewall)}")

    else:
        if network_name and network_purpose:
            parts.append(f"사용자 입력 인프라 설정에 따라 {network_name}은 {_ensure_sentence(network_purpose)}")
        elif network_name:
            parts.append(f"사용자 입력 인프라 설정의 대상 망은 {network_name}입니다.")
        if middleware:
            parts.append(f"기술 스택은 {middleware}을 기준으로 구성합니다.")

    return " ".join(part for part in parts if part)


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


def _normalize_category(category: str) -> str:
    value = str(category or "").strip().lower()

    if value in CATEGORY_LABELS:
        return value

    return _category_from_text(value)


def _category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, CATEGORY_LABELS["general"])


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
            or _component_matches_category(component, category)
        )
    ]

    return matched or [component for component in components if isinstance(component, dict)]


def _component_matches_category(component: dict[str, Any], category: str) -> bool:
    text = (
        f"{component.get('component_id', '')} "
        f"{component.get('name', '')} "
        f"{component.get('description', '')}"
    ).lower()

    aliases = {
        "security": ["auth", "인증", "권한", "security", "보안"],
        "performance": ["cache", "redis", "queue", "성능", "처리량"],
        "quality": ["quality", "품질", "가용성", "안정성", "장애"],
        "operation": ["monitor", "log", "backup", "운영", "로그", "백업"],
        "integration": ["external", "interface", "연계", "외부", "sso", "erp", "api"],
        "deployment": ["server", "gateway", "서버", "망", "배포"],
        "data": ["db", "storage", "store", "데이터", "저장", "파일", "vector"],
    }

    return any(alias in text for alias in aliases.get(category, []))


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

        label = _normalize_text(relation.get("description") or relation.get("label") or "연계")
        selected.append(f"{source} -> {target}({label})")

        if len(selected) >= 4:
            break

    return ", ".join(item for item in selected if item)


def _deployment_summary(
    deployment_environment: dict[str, Any],
    architecture_config: dict[str, Any],
) -> str:
    environment = _normalize_text(deployment_environment.get("environment"))
    network = _normalize_text(deployment_environment.get("network"))
    web_was = _normalize_text(deployment_environment.get("web_was"))
    dbms = _normalize_text(deployment_environment.get("dbms"))
    storage = _normalize_text(deployment_environment.get("storage"))
    hardware = _normalize_text(deployment_environment.get("hardware_spec"))

    parts: list[str] = []

    if network and environment:
        parts.append(f"{network} / {environment}")
    elif network:
        parts.append(network)
    elif environment:
        parts.append(environment)

    if web_was:
        parts.append(f"서버 구성: {web_was}")

    if dbms:
        parts.append(f"DBMS: {dbms}")

    if storage:
        parts.append(f"파일 저장소: {storage}")

    if hardware:
        parts.append(f"인프라 사양: {hardware}")

    networks = architecture_config.get("networks")
    if isinstance(networks, list) and networks:
        network_names = [
            _normalize_text(item.get("prj_net_nm") or item.get("network_name") or "")
            for item in networks
            if isinstance(item, dict)
        ]
        network_names = _dedupe_texts(network_names)
        if network_names:
            parts.append("망 구성: " + ", ".join(network_names))

    return ", ".join(_dedupe_texts(parts))


def _reference_basis_sentence(category: str, references: list[dict[str, Any]]) -> str:
    if not references:
        return ""

    label = _category_label(category)
    ids = _reference_ids(references)
    ids = ids[:5]

    if ids:
        return f"관련 비기능 요구사항({', '.join(ids)})은 {label} 관점의 설계 검토 기준으로 반영합니다."

    return f"관련 비기능 요구사항은 {label} 관점의 설계 검토 기준으로 반영합니다."


def _reference_summary(references: list[dict[str, Any]]) -> str:
    ids = _reference_ids(references)

    if ids:
        return ", ".join(ids[:5])

    titles = []
    for item in _dedupe_references(references)[:3]:
        title = _normalize_text(item.get("title") or "")
        if title:
            titles.append(_shorten(title, 40))

    return ", ".join(titles)


def _reference_ids(references: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []

    for item in references:
        if not isinstance(item, dict):
            continue

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


def _dedupe_references(references: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in references:
        if not isinstance(item, dict):
            continue

        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}

        key = str(
            item.get("requirement_id")
            or item.get("req_id")
            or metadata.get("requirement_id")
            or metadata.get("req_id")
            or item.get("content")
            or item.get("title")
            or item
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(item)

    return result


def _sentence_to_requirement(text: str) -> str:
    normalized = _normalize_text(text).rstrip(".")

    if not normalized:
        return CATEGORY_REQUIREMENT_TEXT["general"]

    replacements = [
        ("반영합니다", "반영해야 함"),
        ("고려합니다", "고려해야 함"),
        ("구성합니다", "구성해야 함"),
        ("적용합니다", "적용해야 함"),
        ("관리합니다", "관리해야 함"),
        ("지원합니다", "지원해야 함"),
        ("제공합니다", "제공해야 함"),
        ("합니다", "해야 함"),
    ]

    for source, target in replacements:
        normalized = normalized.replace(source, target)

    if normalized.endswith(("해야 함", "하여야 함", "해야 한다", "하여야 한다")):
        return normalized

    if normalized.endswith(("함", "한다", "된다")):
        return normalized

    return f"{normalized}을 설계 기준으로 반영해야 함"


def _config_design_hint(config: dict[str, Any]) -> str:
    parts: list[str] = []

    network_name = _first(config.get("network_name"), config.get("prj_net_nm"))
    network_purpose = _first(
        config.get("network_purpose"),
        config.get("network_description"),
        config.get("prj_net_prps"),
    )
    middleware = _first(config.get("middleware_stack"), config.get("mid_stack"))
    firewall = _first(config.get("firewall_setting"), config.get("fwl_settings"))
    auth = _first(config.get("auth_method"))
    hardware = _first(
        config.get("hardware_spec"),
        config.get("server_hardware_spec"),
        config.get("hard_spec"),
    )
    remark = _first(config.get("remark"), config.get("rmrk"))

    if network_name or network_purpose:
        if network_name and network_purpose:
            parts.append(f"사용자 입력 인프라 설정에 따라 {network_name}은 {_ensure_sentence(network_purpose)}")
        elif network_name:
            parts.append(f"사용자 입력 인프라 설정의 대상 망은 {network_name}입니다.")
        elif network_purpose:
            parts.append(f"사용자 입력 인프라 설정의 망 목적은 {_ensure_sentence(network_purpose)}")

    if firewall:
        parts.append(f"망/방화벽 정책으로 {_ensure_sentence(firewall)}")

    if auth:
        parts.append(f"인증 방식은 {auth}을 적용합니다.")

    if middleware:
        parts.append(f"기술 스택은 {middleware}을 기준으로 구성합니다.")

    if hardware:
        parts.append(f"하드웨어 및 인프라 기준은 {hardware}입니다.")

    if remark:
        parts.append(f"운영 담당 범위는 {_ensure_sentence(remark)}")

    return " ".join(part for part in parts if part)


def _cloud_environment(config: dict[str, Any]) -> str:
    value = config.get("is_cloud")

    if value is None:
        value = config.get("cloud_yn")

    if value is True or str(value).upper() == "Y":
        return "클라우드 기반 운영/검증 환경"

    if value is False or str(value).upper() == "N":
        return "내부망 또는 온프레미스 운영/검증 환경"

    return ""


def _infer_web_was(config: dict[str, Any]) -> str:
    text = str(config).lower()

    if "fastapi" in text:
        return "FastAPI API Server"

    if "tomcat" in text:
        return "Tomcat WAS"

    if "spring" in text:
        return "Spring Boot WAS"

    return ""


def _infer_dbms(config: dict[str, Any]) -> str:
    text = str(config).lower()

    for name in ["mysql", "oracle", "postgresql", "mariadb", "sql server"]:
        if name in text:
            return name.upper() if name != "mysql" else "MySQL"

    return ""


def _infer_storage(config: dict[str, Any]) -> str:
    text = str(config).lower()

    if "s3" in text:
        return "S3 Bucket"

    if "nas" in text:
        return "NAS"

    if "object storage" in text:
        return "Object Storage"

    return ""


def _first(*values: Any) -> str:
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _component_name(component: dict[str, Any]) -> str:
    return _first(
        component.get("name"),
        component.get("component_name"),
        component.get("component_id"),
        "컴포넌트",
    )


def _shorten(text: Any, max_length: int) -> str:
    normalized = _normalize_text(text)
    return normalized if len(normalized) <= max_length else normalized[:max_length].rstrip() + "..."


def _normalize_text(text: Any) -> str:
    return " ".join(str(text or "").split()).strip()


def _ensure_sentence(text: Any) -> str:
    value = _normalize_text(text)

    if not value:
        return ""

    if value.endswith((".", "다.", "함.", "함", "요.", "니다.")):
        return value.rstrip(".") + "."

    return value + "."


def _dedupe_texts(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        normalized = _normalize_text(value)
        if not normalized or normalized in seen:
            continue

        seen.add(normalized)
        result.append(normalized)

    return result


def _safe_mermaid_id(value: Any) -> str:
    normalized = re.sub(r"[^0-9A-Za-z_]+", "_", str(value or "NODE").upper()).strip("_")

    if not normalized:
        normalized = "NODE"

    if normalized[0].isdigit():
        normalized = "N_" + normalized

    return normalized


def _escape_mermaid(text: Any) -> str:
    return str(text or "").replace('"', "'").replace("|", "/").replace("\n", " ")