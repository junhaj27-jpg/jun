# 요구사항과 아키텍처 설정을 기반으로 아키텍처 컴포넌트 후보를 생성합니다.
#
# 핵심 원칙:
# - 특정 샘플 row(FastAPI/MySQL/S3 등)에 종속되지 않습니다.
# - mid_stack / middleware_stack의 실제 기술명은 가능한 한 컴포넌트 name에 보존합니다.
# - 기술명은 범용 taxonomy로 역할을 분류하고, 관계/계층은 역할 기반으로 생성될 수 있게 합니다.
# - 언어/ORM/라이브러리처럼 독립 배포 단위가 아닌 기술은 별도 노드가 아니라 관련 컴포넌트 description에 반영합니다.

from __future__ import annotations

import re
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


# 컴포넌트 역할 정의입니다. 기술명은 이 역할로 분류되고, 역할별로 노드명/계층/설명을 생성합니다.
COMPONENT_ROLE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "user_client": {
        "component_id": "USER_CLIENT",
        "default_name": "사용자/클라이언트",
        "layer": "External Actor",
        "description": "사용자 또는 외부 클라이언트가 시스템 기능을 요청하는 진입 주체입니다.",
    },
    "api_gateway": {
        "component_id": "API_GATEWAY",
        "default_name": "API 게이트웨이",
        "layer": "Presentation Layer",
        "description": "외부 요청을 수신하고 내부 서비스로 라우팅하는 API 진입점입니다.",
    },
    "api_service": {
        "component_id": "API_SERVICE",
        "default_name": "API 서비스",
        "layer": "Application Layer",
        "description": "업무 API 요청을 처리하고 인증, 상태 조회, 데이터 저장 요청을 조정하는 서비스입니다.",
    },
    "auth_service": {
        "component_id": "AUTH_SERVICE",
        "default_name": "인증/인가 서비스",
        "layer": "Application Layer",
        "description": "사용자 인증, 서비스 간 인증, 권한 검증을 수행하는 보안 컴포넌트입니다.",
    },
    "workflow_service": {
        "component_id": "WORKFLOW_SERVICE",
        "default_name": "Workflow/작업 처리 서비스",
        "layer": "Agent Orchestration Layer",
        "description": "업무 처리 흐름, 배치, 비동기 작업, 산출물 생성 작업을 오케스트레이션하는 컴포넌트입니다.",
    },
    "ai_llm_service": {
        "component_id": "AI_LLM_SERVICE",
        "default_name": "AI/LLM 서비스",
        "layer": "AI/LLM Layer",
        "description": "LLM 추론, 임베딩, RAG 기반 응답 생성을 수행하는 AI 처리 컴포넌트입니다.",
    },
    "vector_db": {
        "component_id": "VECTOR_DB",
        "default_name": "Vector DB",
        "layer": "Data Layer",
        "description": "문서 임베딩과 의미 검색 인덱스를 저장하는 벡터 저장소입니다.",
    },
    "rdbms": {
        "component_id": "RDBMS",
        "default_name": "RDBMS",
        "layer": "Data Layer",
        "description": "업무 데이터, 메타데이터, 처리 상태를 저장하는 관계형 데이터베이스입니다.",
    },
    "nosql_db": {
        "component_id": "NOSQL_DB",
        "default_name": "NoSQL 저장소",
        "layer": "Data Layer",
        "description": "문서형, 키-값, 컬럼형 등 비정형 업무 데이터를 저장하는 NoSQL 저장소입니다.",
    },
    "file_storage": {
        "component_id": "FILE_STORAGE",
        "default_name": "파일 저장소",
        "layer": "Data Layer",
        "description": "입력 파일, 첨부 파일, 생성 산출물을 저장하는 파일 저장소입니다.",
    },
    "cache_store": {
        "component_id": "CACHE_STORE",
        "default_name": "캐시/세션 저장소",
        "layer": "Data Layer",
        "description": "세션, 캐시, 임시 상태 데이터를 저장해 응답 성능을 보조하는 저장소입니다.",
    },
    "message_queue": {
        "component_id": "MESSAGE_QUEUE",
        "default_name": "메시지 큐/이벤트 브로커",
        "layer": "Agent Orchestration Layer",
        "description": "비동기 작업 요청과 이벤트 메시지를 전달하는 큐 또는 브로커 컴포넌트입니다.",
    },
    "search_engine": {
        "component_id": "SEARCH_ENGINE",
        "default_name": "검색 엔진",
        "layer": "Data Layer",
        "description": "키워드 검색, 로그 검색, 전문 검색 인덱스를 제공하는 검색 컴포넌트입니다.",
    },
    "external_system": {
        "component_id": "EXTERNAL_SYSTEM",
        "default_name": "외부 연계 시스템",
        "layer": "External Integration Layer",
        "description": "외부 기관 또는 내부 타 시스템과 데이터를 송수신하는 연계 대상입니다.",
    },
    "monitoring_log": {
        "component_id": "MONITORING_LOG",
        "default_name": "모니터링/로그 시스템",
        "layer": "Operation Layer",
        "description": "처리 이력, 오류, 성능 지표, 감사 로그를 수집하는 운영 컴포넌트입니다.",
    },
    "backup_restore": {
        "component_id": "BACKUP_RESTORE",
        "default_name": "백업/복구 시스템",
        "layer": "Operation Layer",
        "description": "주요 데이터와 파일을 백업하고 장애 시 복구를 지원하는 운영 컴포넌트입니다.",
    },
    "deployment_platform": {
        "component_id": "DEPLOYMENT_PLATFORM",
        "default_name": "배포/컨테이너 플랫폼",
        "layer": "Operation Layer",
        "description": "컨테이너, 오케스트레이션, 배포 자동화, 런타임 운영을 지원하는 플랫폼입니다.",
    },
}


# 범용 기술 역할 분류 규칙입니다. 특정 샘플 값을 위한 하드코딩이 아니라, 기술명을 역할로 분류하기 위한 taxonomy입니다.
# 새 기술을 지원하려면 여기 키워드만 추가하면 됩니다.
TECH_ROLE_RULES: list[dict[str, Any]] = [
    {
        "role": "api_gateway",
        "keywords": [
            "api gateway", "gateway", "게이트웨이", "reverse proxy", "proxy", "nginx", "apache",
            "load balancer", "loadbalancer", "로드밸런서", "alb", "nlb", "ingress",
        ],
    },
    {
        "role": "api_service",
        "keywords": [
            "api", "rest", "graphql", "was", "application server", "app server", "업무 api", "api 서버",
            "spring", "spring boot", "egov", "egovframework", "전자정부프레임워크", "fastapi", "django", "flask",
            "express", "nestjs", "nest.js", "node", "node.js", "nodejs", "asp.net", ".net", "laravel", "rails",
            "tomcat", "jeus", "weblogic", "websphere", "gin", "fiber",
        ],
    },
    {
        "role": "auth_service",
        "keywords": [
            "auth", "authentication", "authorization", "인증", "인가", "권한", "sso", "oauth", "oauth2",
            "oidc", "jwt", "api key", "api-key", "keycloak", "cognito", "iam", "ldap", "ad", "active directory",
        ],
    },
    {
        "role": "workflow_service",
        "keywords": [
            "workflow", "워크플로우", "orchestration", "오케스트레이션", "scheduler", "스케줄러", "batch", "배치",
            "worker", "작업", "job", "queue worker", "airflow", "celery", "temporal", "argo", "step functions", "langgraph",
            "agent", "supervisor", "quartz", "cron", "산출물 생성",
        ],
    },
    {
        "role": "ai_llm_service",
        "keywords": [
            "ai", "llm", "vlm", "sllm", "rag", "inference", "추론", "model", "모델", "embedding", "임베딩",
            "openai", "azure openai", "claude", "gemini", "qwen", "llama", "mistral", "vllm", "ollama", "tgi",
        ],
    },
    {
        "role": "vector_db",
        "keywords": [
            "vector", "vector db", "vector database", "벡터", "벡터db", "벡터 db", "qdrant", "milvus", "weaviate",
            "pinecone", "chroma", "faiss", "pgvector", "opensearch vector",
        ],
    },
    {
        "role": "rdbms",
        "keywords": [
            "rdb", "rdbms", "dbms", "database", "데이터베이스", "db", "rds", "aurora", "mysql", "mariadb",
            "postgresql", "postgres", "oracle", "tibero", "sql server", "mssql", "db2", "cubrid", "altibase", "sqlite",
        ],
    },
    {
        "role": "nosql_db",
        "keywords": [
            "nosql", "mongodb", "mongo", "dynamodb", "cassandra", "hbase", "couchbase", "document db", "documentdb",
            "wide column", "key-value", "key value",
        ],
    },
    {
        "role": "file_storage",
        "keywords": [
            "object storage", "objectstore", "오브젝트", "bucket", "버킷", "s3", "minio", "obs", "oss",
            "blob storage", "azure blob", "gcs", "cloud storage", "파일 저장소", "file storage", "스토리지", "storage",
            "nas", "nfs", "efs", "file share", "첨부", "산출물 파일", "업로드 파일",
        ],
    },
    {
        "role": "cache_store",
        "keywords": [
            "cache", "캐시", "session", "세션", "redis", "memcached", "elasticache", "hazelcast",
        ],
    },
    {
        "role": "message_queue",
        "keywords": [
            "queue", "mq", "message queue", "메시지 큐", "event", "이벤트", "event bus", "broker", "브로커",
            "kafka", "rabbitmq", "sqs", "sns", "pubsub", "pub/sub", "activemq", "nats", "pulsar", "stream",
        ],
    },
    {
        "role": "search_engine",
        "keywords": [
            "search", "검색", "elasticsearch", "opensearch", "solr", "lucene", "검색엔진", "전문검색",
        ],
    },
    {
        "role": "monitoring_log",
        "keywords": [
            "monitoring", "모니터링", "log", "로그", "audit", "감사", "observability", "관측", "metric", "metrics",
            "prometheus", "grafana", "elk", "efk", "kibana", "logstash", "fluentd", "fluentbit", "cloudwatch",
            "opentelemetry", "alert", "알림", "장애", "관제",
        ],
    },
    {
        "role": "backup_restore",
        "keywords": [
            "backup", "백업", "restore", "복구", "dr", "disaster recovery", "재해복구", "snapshot", "스냅샷",
        ],
    },
    {
        "role": "deployment_platform",
        "keywords": [
            "kubernetes", "k8s", "eks", "aks", "gke", "openshift", "docker", "container", "컨테이너",
            "helm", "argocd", "jenkins", "gitlab ci", "github actions", "ci/cd", "cicd",
        ],
    },
]


SUPPORT_TECH_RULES: list[dict[str, Any]] = [
    {
        "kind": "language_runtime",
        "keywords": [
            "python", "java", "javascript", "typescript", "node runtime", "kotlin", "scala", "c#", "csharp", "go", "golang",
            "php", "ruby", "rust", "runtime", "jvm", ".net runtime",
        ],
    },
    {
        "kind": "db_access",
        "keywords": [
            "orm", "sql mapper", "sqlalchemy", "jpa", "hibernate", "mybatis", "prisma", "sequelize", "jdbc", "odbc",
        ],
    },
    {
        "kind": "frontend_library",
        "keywords": [
            "react", "vue", "angular", "svelte", "next.js", "nextjs", "nuxt", "frontend", "프론트엔드", "ui",
        ],
    },
]


TEXT_ROLE_HINTS: dict[str, list[str]] = {
    "user_client": ["사용자", "클라이언트", "포털", "화면", "브라우저", "요청"],
    "api_gateway": ["게이트웨이", "gateway", "reverse proxy", "로드밸런서", "load balancer"],
    "api_service": ["api 서버", "업무 api", "was", "서비스", "요청 처리"],
    "auth_service": ["인증", "인가", "권한", "sso", "api key", "jwt", "oauth"],
    "workflow_service": ["워크플로우", "workflow", "배치", "작업", "산출물 생성", "오케스트레이션"],
    "ai_llm_service": ["llm", "ai", "rag", "추론", "모델", "임베딩"],
    "vector_db": ["vector", "벡터", "임베딩 저장"],
    "rdbms": ["db", "database", "데이터베이스", "rdbms", "rds", "상태 저장", "메타데이터"],
    "nosql_db": ["nosql", "문서형", "key-value"],
    "file_storage": ["파일", "첨부", "산출물", "업로드", "다운로드", "스토리지", "bucket", "오브젝트"],
    "cache_store": ["캐시", "cache", "세션"],
    "message_queue": ["큐", "queue", "비동기", "이벤트", "broker"],
    "search_engine": ["검색", "search", "전문검색"],
    "external_system": ["외부", "연계", "인터페이스", "타 시스템", "기관", "erp", "legacy"],
    "monitoring_log": ["모니터링", "로그", "감사", "장애", "관제", "알림"],
    "backup_restore": ["백업", "복구", "dr", "재해복구"],
}


ROLE_ORDER = [
    "user_client",
    "api_gateway",
    "api_service",
    "auth_service",
    "workflow_service",
    "message_queue",
    "ai_llm_service",
    "vector_db",
    "rdbms",
    "nosql_db",
    "file_storage",
    "cache_store",
    "search_engine",
    "external_system",
    "monitoring_log",
    "backup_restore",
    "deployment_platform",
]


ROLE_COMPONENT_ID = {role: definition["component_id"] for role, definition in COMPONENT_ROLE_DEFINITIONS.items()}
COMPONENT_ID_ROLE = {component_id: role for role, component_id in ROLE_COMPONENT_ID.items()}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

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
    selected = [
        {"driver_id": f"DRV-{index + 1:03d}", "category": category, "name": name, "description": description}
        for index, (category, name, description) in enumerate(drivers)
        if _has_category(text, category)
    ]
    return selected or [
        {"driver_id": "DRV-001", "category": "deployment", "name": "배포 Driver", "description": "서버 구성과 네트워크 구성을 아키텍처에 반영합니다."},
        {"driver_id": "DRV-002", "category": "security", "name": "보안 Driver", "description": "인증, 접근 제어, 통신 보안 요구사항을 반영합니다."},
        {"driver_id": "DRV-003", "category": "data", "name": "데이터 관리 Driver", "description": "데이터 저장소와 파일 저장소 구성을 반영합니다."},
    ]


def build_component_candidates(
    requirements: list[dict[str, Any]],
    architecture_config: dict[str, Any],
    drivers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    # 사용자가 명시한 components는 최우선 근거입니다.
    # 단, 여기서 바로 return하지 않습니다. 명시 components가 있더라도 mid_stack/hard_spec에
    # DB, 저장소, 큐, 모니터링 같은 구성요소가 추가로 적혀 있을 수 있으므로 함께 병합합니다.
    explicit_components = _explicit_components_from_config(architecture_config)

    raw_text = _combined_text(requirements, architecture_config, lowercase=False)
    lower_text = raw_text.lower()

    stack_info = _parse_stack_info(architecture_config)
    role_techs: dict[str, list[str]] = {role: list(values) for role, values in (stack_info.get("role_techs") or {}).items()}
    support_techs: dict[str, list[str]] = {kind: list(values) for kind, values in (stack_info.get("support_techs") or {}).items()}

    # 자연어 설정/요구사항에서 역할이 명시된 경우 보강합니다. 기술명은 없으면 일반명으로 생성합니다.
    for role, keywords in TEXT_ROLE_HINTS.items():
        if role in role_techs:
            continue
        if _contains_any(lower_text, keywords):
            role_techs.setdefault(role, [])

    # 업무 API/서비스/워크플로우 등 처리 컴포넌트가 있으면 사용자 진입점을 보강합니다.
    if any(role in role_techs for role in ["api_gateway", "api_service", "workflow_service", "ai_llm_service"]):
        role_techs.setdefault("user_client", [])

    # 저장/파일 관련 텍스트는 기술명이 없어도 최소 저장소 컴포넌트를 보강합니다.
    if _contains_any(lower_text, ["상태", "메타데이터", "업무 데이터", "db 저장", "데이터 저장", "database", "rdbms"]):
        role_techs.setdefault("rdbms", [])
    if _contains_any(lower_text, ["파일", "첨부", "산출물", "업로드", "다운로드", "object storage", "bucket", "스토리지"]):
        role_techs.setdefault("file_storage", [])

    inferred_components = [_component_from_role(role, role_techs.get(role) or [], architecture_config) for role in ROLE_ORDER if role in role_techs]

    if explicit_components:
        components = _merge_explicit_and_inferred_components(explicit_components, inferred_components)
    else:
        components = inferred_components

    if not components:
        components = [
            _component_from_role("user_client", [], architecture_config),
            _component_from_role("api_service", [], architecture_config),
            _component_from_role("rdbms", [], architecture_config),
        ]

    components = _apply_support_technologies(components, support_techs)
    return _attach_driver_categories(normalize_components(components), drivers)


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




def _explicit_components_from_config(architecture_config: dict[str, Any]) -> list[dict[str, Any]]:
    """사용자가 명시한 시스템 구성요소를 다양한 key에서 수집합니다.

    운영 DB나 API에서 명시 components가 들어올 수 있는 이름이 프로젝트마다 다를 수 있으므로
    components/system_components/architecture_components/component_list를 모두 허용합니다.
    """
    candidates = None
    for key in ["components", "system_components", "architecture_components", "component_list"]:
        value = architecture_config.get(key)
        if isinstance(value, list) and value:
            candidates = value
            break
    if not candidates:
        return []

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(candidates, start=1):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or item.get("type") or item.get("component_type") or "")
        layer = str(item.get("layer") or _layer_from_role_name(role) or "Application Layer")
        name = str(item.get("name") or item.get("component_name") or item.get("component_nm") or f"명시 구성요소 {index}")
        component_id = str(item.get("component_id") or item.get("id") or _safe_id(name))
        normalized.append(
            {
                **item,
                "component_id": component_id,
                "name": name,
                "layer": layer,
                "description": str(item.get("description") or item.get("desc") or item.get("role_description") or item.get("role") or ""),
                "source": item.get("source") or "user_explicit_components",
                "technologies": item.get("technologies") if isinstance(item.get("technologies"), list) else [],
            }
        )
    return normalize_components(normalized)


def _layer_from_role_name(role: str) -> str:
    role_text = str(role).lower()
    if not role_text:
        return ""
    if any(word in role_text for word in ["client", "user", "actor", "사용자", "클라이언트"]):
        return "External Actor"
    if any(word in role_text for word in ["gateway", "web", "proxy", "presentation", "게이트웨이", "프록시"]):
        return "Presentation Layer"
    if any(word in role_text for word in ["workflow", "batch", "worker", "queue", "agent", "워크플로우", "배치", "작업"]):
        return "Agent Orchestration Layer"
    if any(word in role_text for word in ["llm", "ai", "rag", "model", "모델", "추론"]):
        return "AI/LLM Layer"
    if any(word in role_text for word in ["db", "database", "storage", "cache", "vector", "data", "저장", "데이터"]):
        return "Data Layer"
    if any(word in role_text for word in ["external", "interface", "integration", "연계", "외부"]):
        return "External Integration Layer"
    if any(word in role_text for word in ["monitor", "log", "backup", "operation", "운영", "로그", "백업"]):
        return "Operation Layer"
    return "Application Layer"


def _merge_explicit_and_inferred_components(
    explicit_components: list[dict[str, Any]],
    inferred_components: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """사용자 명시 구성요소와 mid_stack/hard_spec 추론 구성요소를 병합합니다.

    - 명시 구성요소는 기본적으로 보존합니다.
    - 명시 구성요소가 일반명이고, mid_stack에서 더 구체적인 기술명이 나오면 기술명을 보강합니다.
    - 같은 역할의 구성요소가 여러 개면 모두 보존합니다.
    """
    explicit = normalize_components(explicit_components or [])
    inferred = normalize_components(inferred_components or [])
    if not explicit:
        return inferred
    if not inferred:
        return explicit

    merged: list[dict[str, Any]] = []
    used_inferred_ids: set[str] = set()

    for item in explicit:
        role = _infer_role_from_component(item)
        same_role = [candidate for candidate in inferred if _infer_role_from_component(candidate) == role]
        stack_named = next((candidate for candidate in same_role if _is_stack_named_component(candidate)), None)
        if stack_named and not _is_stack_named_component(item) and _is_generic_component_name(item):
            merged_item = _merge_one_component(item, stack_named)
            used_inferred_ids.add(str(stack_named.get("component_id")))
            merged.append(merged_item)
        else:
            merged.append(item)

    existing_ids = {str(component.get("component_id")) for component in merged}
    for item in inferred:
        cid = str(item.get("component_id"))
        if cid and cid not in existing_ids and cid not in used_inferred_ids:
            merged.append(item)
            existing_ids.add(cid)

    return normalize_components(merged)


def _is_generic_component_name(component: dict[str, Any]) -> bool:
    name = str(component.get("name") or "").lower().strip()
    if not name:
        return True
    generic_words = [
        "api 서버", "api service", "api 서비스", "업무 서비스", "서비스",
        "db", "database", "데이터베이스", "rdbms", "파일 저장소", "저장소", "스토리지",
        "캐시", "검색 엔진", "외부 연계 시스템", "모니터링", "로그 시스템",
    ]
    return any(name == word or name.endswith(word) for word in generic_words)

def merge_components_with_stack_fallback(
    llm_components: list[Any],
    fallback_components: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """LLM 결과가 일반명으로 뭉개더라도 mid_stack 기반 기술명을 보존합니다.

    LLM이 ``파일 저장소``처럼 일반명을 반환하면 Mermaid 노드에도 기술명이 빠집니다.
    이 함수는 fallback_components에 들어있는 ``technologies``/``source=mid_stack`` 값을 기준으로
    같은 역할의 컴포넌트명을 다시 ``S3 오브젝트/파일 저장소`` 같은 실제 기술명으로 보정합니다.

    규칙은 특정 샘플 기술명이 아니라 ROLE taxonomy 기준입니다.
    """
    llm_normalized = normalize_components(llm_components or [])
    fallback_normalized = normalize_components(fallback_components or [])

    if not llm_normalized:
        return fallback_normalized
    if not fallback_normalized:
        return llm_normalized

    llm_by_role: dict[str, dict[str, Any]] = {}
    llm_unmatched: list[dict[str, Any]] = []
    for component in llm_normalized:
        role = _infer_role_from_component(component)
        if role and role not in llm_by_role:
            llm_by_role[role] = component
        else:
            llm_unmatched.append(component)

    fallback_by_role: dict[str, dict[str, Any]] = {}
    for component in fallback_normalized:
        role = _infer_role_from_component(component)
        if role and role not in fallback_by_role:
            fallback_by_role[role] = component

    merged: list[dict[str, Any]] = []
    used_llm_ids: set[str] = set()
    used_fallback_ids: set[str] = set()

    for role in ROLE_ORDER:
        llm_component = llm_by_role.get(role)
        fallback_component = fallback_by_role.get(role)

        if fallback_component and _is_stack_named_component(fallback_component):
            item = _merge_one_component(llm_component, fallback_component)
            merged.append(item)
            used_fallback_ids.add(str(fallback_component.get("component_id")))
            if llm_component:
                used_llm_ids.add(str(llm_component.get("component_id")))
            continue

        if llm_component:
            merged.append(llm_component)
            used_llm_ids.add(str(llm_component.get("component_id")))
            continue

        if fallback_component:
            merged.append(fallback_component)
            used_fallback_ids.add(str(fallback_component.get("component_id")))

    # fallback에 같은 역할의 세부 구성요소가 여러 개 있으면 모두 보존합니다.
    # 예: 외부 연계 시스템 3개, DB 2개, 파일 저장소 2개 등.
    existing_ids = {str(item.get("component_id")) for item in merged}
    for component in fallback_normalized:
        cid = str(component.get("component_id"))
        if cid and cid not in existing_ids and cid not in used_fallback_ids:
            merged.append(component)
            existing_ids.add(cid)

    # LLM이 세부 서비스/외부 시스템을 추가로 식별한 경우도 가능한 한 보존합니다.
    # 단, 같은 component_id 중복만 제거합니다.
    for component in llm_normalized:
        cid = str(component.get("component_id"))
        if cid and cid not in used_llm_ids and cid not in existing_ids:
            merged.append(component)
            existing_ids.add(cid)

    return normalize_components(merged)


def _merge_one_component(llm_component: dict[str, Any] | None, fallback_component: dict[str, Any]) -> dict[str, Any]:
    if not llm_component:
        return dict(fallback_component)

    # 이름/ID/계층/기술명은 mid_stack 기반 fallback을 우선합니다.
    # LLM description은 보조 설명으로만 합칩니다.
    item = dict(llm_component)
    item["component_id"] = fallback_component.get("component_id") or item.get("component_id")
    item["name"] = fallback_component.get("name") or item.get("name")
    item["layer"] = fallback_component.get("layer") or item.get("layer")
    item["technologies"] = fallback_component.get("technologies") or item.get("technologies") or []
    item["source"] = fallback_component.get("source") or item.get("source") or "architecture_config"

    fallback_desc = str(fallback_component.get("description") or "").strip()
    llm_desc = str(llm_component.get("description") or "").strip()
    if fallback_desc and llm_desc and fallback_desc not in llm_desc and llm_desc not in fallback_desc:
        item["description"] = f"{fallback_desc} {llm_desc}"
    else:
        item["description"] = fallback_desc or llm_desc

    if fallback_component.get("driver_categories"):
        item["driver_categories"] = fallback_component.get("driver_categories")
    return item


def _is_stack_named_component(component: dict[str, Any]) -> bool:
    technologies = component.get("technologies")
    if isinstance(technologies, list) and any(str(value).strip() for value in technologies):
        return True
    return str(component.get("source") or "").lower() == "mid_stack"


def _infer_role_from_component(component: dict[str, Any]) -> str:
    component_id = _safe_id(str(component.get("component_id") or ""))
    if component_id in COMPONENT_ID_ROLE:
        return COMPONENT_ID_ROLE[component_id]

    text = f"{component.get('component_id', '')} {component.get('name', '')} {component.get('layer', '')} {component.get('description', '')}".lower()

    # 우선순위가 중요합니다. object/file storage가 'storage' 때문에 일반 data로 뭉개지지 않도록 먼저 봅니다.
    checks = [
        ("user_client", ["user", "client", "사용자", "클라이언트", "external actor"]),
        ("api_gateway", ["gateway", "게이트웨이", "reverse proxy", "proxy", "nginx", "apache", "presentation layer"]),
        ("auth_service", ["auth", "인증", "인가", "권한", "sso", "oauth", "jwt", "api key"]),
        ("workflow_service", ["workflow", "워크플로우", "worker", "batch", "배치", "job", "작업 처리", "orchestration", "agent orchestration"]),
        ("ai_llm_service", ["llm", "ai/llm", "ai service", "ai 서비스", "rag", "추론", "모델"]),
        ("vector_db", ["vector", "벡터", "qdrant", "milvus", "weaviate", "embedding", "임베딩"]),
        ("cache_store", ["redis", "cache", "캐시", "session", "세션"]),
        ("message_queue", ["kafka", "rabbitmq", "queue", "mq", "메시지", "broker", "브로커", "event bus"]),
        ("search_engine", ["search", "검색", "opensearch", "elasticsearch", "solr"]),
        ("file_storage", ["s3", "minio", "object storage", "object", "bucket", "blob", "gcs", "oss", "obs", "nas", "nfs", "파일 저장", "파일 저장소", "스토리지", "storage"]),
        ("rdbms", ["rdbms", "rds", "oracle", "mysql", "mariadb", "postgres", "postgresql", "tibero", "mssql", "sql server", "dbms", " database", " db", "데이터베이스"]),
        ("nosql_db", ["nosql", "mongodb", "dynamodb", "cassandra", "documentdb"]),
        ("external_system", ["external", "외부", "연계", "interface", "인터페이스", "타 시스템"]),
        ("monitoring_log", ["monitoring", "모니터링", "log", "로그", "prometheus", "grafana", "elk", "관제"]),
        ("backup_restore", ["backup", "백업", "restore", "복구", "dr", "재해복구"]),
        ("deployment_platform", ["kubernetes", "k8s", "docker", "container", "컨테이너", "ci/cd", "cicd"]),
        ("api_service", ["api", "was", "tomcat", "spring", "fastapi", "django", "express", "application layer", "업무 서비스"]),
    ]
    for role, keywords in checks:
        if any(keyword in text for keyword in keywords):
            return role
    return ""

def apply_architecture_changes(components:list[dict[str,Any]],changes:list[dict[str,Any]])->list[dict[str,Any]]:
    updated=[dict(component) for component in components]
    by_id={component["component_id"]:component for component in updated if isinstance(component,dict) and component.get("component_id")}
    for change in changes:
        if not isinstance(change,dict):
            continue
        operation=str(change.get("change_type") or change.get("operation") or "").upper()
        target=change.get("item") if isinstance(change.get("item"),dict) else change
        raw_id=target.get("component_id") or change.get("component_id")
        name=str(target.get("component_name") or target.get("name") or target.get("target") or change.get("component_name") or change.get("name") or "").strip()
        if not raw_id and not name:
            continue
        component_id=_safe_id(str(raw_id or name))
        new_description=target.get("description") or change.get("description")
        new_layer=target.get("layer") or change.get("layer")
        if operation in {"DELETE","REMOVE"}:
            updated=[component for component in updated if component.get("component_id")!=component_id]
            by_id.pop(component_id,None)
            continue
        if operation in {"UPDATE","MODIFY","CHANGE"}:
            if component_id not in by_id:
                continue
            component=by_id[component_id]
            if name:
                component["name"]=name
            if new_layer:
                component["layer"]=str(new_layer)
            if new_description:
                component["description"]=str(new_description)
            continue
        if component_id not in by_id:
            component={"component_id":component_id,"name":name or component_id,"layer":str(new_layer or "Application Layer"),"description":str(new_description or "회의록 변경사항으로 추가된 컴포넌트입니다.")}
            updated.append(component)
            by_id[component_id]=component
        else:
            component=by_id[component_id]
            if name:
                component["name"]=name
            if new_layer:
                component["layer"]=str(new_layer)
            if new_description:
                component["description"]=str(new_description)
    return normalize_components(updated)


# ---------------------------------------------------------------------------
# Component inference helpers
# ---------------------------------------------------------------------------

def _parse_stack_info(architecture_config: dict[str, Any]) -> dict[str, Any]:
    stack_text = str(
        architecture_config.get("middleware_stack")
        or architecture_config.get("mid_stack")
        or architecture_config.get("technology_stack")
        or ""
    )
    context_text = _config_text(architecture_config)
    tokens = _split_stack_tokens(stack_text)

    role_techs: dict[str, list[str]] = {}
    support_techs: dict[str, list[str]] = {}
    unclassified: list[str] = []

    for token in tokens:
        support_kind = _classify_support_tech(token)
        if support_kind:
            support_techs.setdefault(support_kind, []).append(_display_token(token))
            continue

        role = _classify_component_role(token)
        if role:
            role_techs.setdefault(role, []).append(_display_token(token))
        else:
            unclassified.append(_display_token(token))

    # mid_stack이 빈 경우, config 전체 문장에 명시된 기술/역할 키워드도 보조적으로 반영합니다.
    # 이때도 특정 샘플 기술이 아니라 taxonomy 기준으로만 판단합니다.
    context_lower = context_text.lower()
    for rule in TECH_ROLE_RULES:
        role = str(rule["role"])
        if role in role_techs:
            continue
        matched = _first_matching_keyword(context_lower, rule.get("keywords") or [])
        if matched:
            # 문장 속 기술명을 안정적으로 뽑기 어려우면 일반 역할 컴포넌트로 생성하고, name은 role default를 사용합니다.
            role_techs.setdefault(role, [])

    for rule in SUPPORT_TECH_RULES:
        kind = str(rule["kind"])
        if kind in support_techs:
            continue
        matched = _first_matching_keyword(context_lower, rule.get("keywords") or [])
        if matched:
            support_techs.setdefault(kind, []).append(_display_token(matched))

    return {
        "raw_stack": stack_text,
        "tokens": tokens,
        "role_techs": {key: _unique_strings(value) for key, value in role_techs.items()},
        "support_techs": {key: _unique_strings(value) for key, value in support_techs.items()},
        "unclassified": _unique_strings(unclassified),
    }


def _split_stack_tokens(value: str) -> list[str]:
    if not value:
        return []
    text = str(value)
    text = text.replace("ㆍ", ",").replace("·", ",").replace("•", ",")
    text = re.sub(r"\s+[+]\s+", ",", text)
    text = text.replace(" / ", ",").replace("/", ",")
    parts = re.split(r"[,;\n\r|]+", text)
    tokens: list[str] = []
    for part in parts:
        token = " ".join(part.strip(" -•\t").split())
        if token:
            tokens.append(token)
    return _unique_strings(tokens)


def _classify_component_role(token: str) -> str:
    lower = token.lower()

    # DB 같은 짧은 토큰은 오탐 가능성이 높아 단어 경계로 한 번 더 봅니다.
    for rule in TECH_ROLE_RULES:
        role = str(rule["role"])
        for keyword in rule.get("keywords") or []:
            kw = str(keyword).lower().strip()
            if not kw:
                continue
            if _keyword_matches(lower, kw):
                return role
    return ""


def _classify_support_tech(token: str) -> str:
    lower = token.lower()
    for rule in SUPPORT_TECH_RULES:
        kind = str(rule["kind"])
        for keyword in rule.get("keywords") or []:
            kw = str(keyword).lower().strip()
            if kw and _keyword_matches(lower, kw):
                return kind
    return ""


def _keyword_matches(text: str, keyword: str) -> bool:
    if len(keyword) <= 3 and keyword.isalnum():
        return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text) is not None
    return keyword in text


def _first_matching_keyword(text: str, keywords: list[str]) -> str:
    for keyword in keywords:
        kw = str(keyword).lower().strip()
        if kw and _keyword_matches(text, kw):
            return keyword
    return ""


def _component_from_role(role: str, techs: list[str], architecture_config: dict[str, Any]) -> dict[str, Any]:
    definition = COMPONENT_ROLE_DEFINITIONS[role]
    name = _make_component_name(role, techs, architecture_config)
    description = _make_component_description(role, name, techs, architecture_config)
    return {
        "component_id": definition["component_id"],
        "name": name,
        "layer": definition["layer"],
        "description": description,
        "source": "mid_stack" if techs else "architecture_config_or_requirements",
        "technologies": _unique_strings(techs),
    }


def _make_component_name(role: str, techs: list[str], architecture_config: dict[str, Any]) -> str:
    definition = COMPONENT_ROLE_DEFINITIONS[role]
    techs = _unique_strings([_display_token(tech) for tech in techs])
    joined = _join_techs(techs)
    context = _config_text(architecture_config).lower()

    if not joined:
        return str(definition["default_name"])

    if role == "api_gateway":
        if _contains_any(joined.lower(), ["proxy", "nginx", "apache"]):
            return f"{joined} Reverse Proxy/API 게이트웨이"
        return f"{joined} API 게이트웨이" if "gateway" not in joined.lower() and "게이트웨이" not in joined else joined

    if role == "api_service":
        return f"{joined} API 서버" if len(techs) == 1 else f"{joined} API 서비스"

    if role == "auth_service":
        return f"{joined} 인증/인가 서비스"

    if role == "workflow_service":
        return f"{joined} Workflow/작업 처리 서버" if len(techs) == 1 else f"{joined} Workflow/작업 처리 서비스"

    if role == "ai_llm_service":
        return f"{joined} LLM/AI 서비스"

    if role == "vector_db":
        return f"{joined} Vector DB"

    if role == "rdbms":
        # RDS/Aurora 같은 관리형 DB 표기가 설정에 있으면 DB 벤더명과 함께 보존합니다.
        if _contains_any(context, ["rds", "aurora", "cloud sql", "managed db", "관리형"]):
            return f"{joined} RDS" if "rds" not in joined.lower() and "aurora" not in joined.lower() else joined
        return f"{joined} DB" if not _ends_with_any(joined.lower(), ["db", "database", "rdbms"]) else joined

    if role == "nosql_db":
        return f"{joined} NoSQL 저장소" if "nosql" not in joined.lower() else joined

    if role == "file_storage":
        lower = joined.lower()
        if _contains_any(lower, ["s3", "minio", "object", "blob", "bucket", "gcs", "oss", "obs"]):
            return f"{joined} 오브젝트/파일 저장소" if not _contains_any(lower, ["storage", "스토리지", "저장소"]) else joined
        return f"{joined} 파일 저장소" if not _contains_any(lower, ["storage", "스토리지", "저장소"]) else joined

    if role == "cache_store":
        return f"{joined} 캐시/세션 저장소"

    if role == "message_queue":
        return f"{joined} 메시지 큐/이벤트 브로커"

    if role == "search_engine":
        return f"{joined} 검색 엔진" if "search" not in joined.lower() and "검색" not in joined else joined

    if role == "monitoring_log":
        return f"{joined} 모니터링/로그 시스템"

    if role == "backup_restore":
        return f"{joined} 백업/복구 시스템"

    if role == "deployment_platform":
        return f"{joined} 배포/컨테이너 플랫폼"

    return joined


def _make_component_description(role: str, name: str, techs: list[str], architecture_config: dict[str, Any]) -> str:
    definition = COMPONENT_ROLE_DEFINITIONS[role]
    base = str(definition["description"])
    tech_text = ", ".join(_unique_strings(techs))
    network = architecture_config.get("network_name") or architecture_config.get("prj_net_nm")
    prefix = f"{name}는 "
    description = prefix + base
    if tech_text:
        description += f" 적용 기술은 {tech_text}입니다."
    if network and role in {"api_gateway", "api_service", "workflow_service"}:
        description += f" {network}의 주요 처리 흐름에 포함됩니다."
    return description


def _apply_support_technologies(components: list[dict[str, Any]], support_techs: dict[str, list[str]]) -> list[dict[str, Any]]:
    languages = _unique_strings(support_techs.get("language_runtime") or [])
    db_access = _unique_strings(support_techs.get("db_access") or [])
    frontend = _unique_strings(support_techs.get("frontend_library") or [])

    result: list[dict[str, Any]] = []
    has_api = any(str(item.get("component_id")) == "API_SERVICE" for item in components)

    for component in components:
        item = dict(component)
        cid = str(item.get("component_id") or "")
        extras: list[str] = []

        if cid in {"API_SERVICE", "WORKFLOW_SERVICE"} and languages:
            extras.append(f"구현 언어/런타임은 {', '.join(languages)}를 사용합니다")
        if cid in {"API_SERVICE", "RDBMS", "NOSQL_DB"} and db_access:
            extras.append(f"DB 접근은 {', '.join(db_access)} 기반으로 처리합니다")
        if cid in {"USER_CLIENT", "API_GATEWAY"} and frontend:
            extras.append(f"프론트엔드 기술은 {', '.join(frontend)}를 반영합니다")
        elif cid == "API_SERVICE" and frontend and not has_api:
            extras.append(f"프론트엔드 연계 기술은 {', '.join(frontend)}를 반영합니다")

        if extras:
            desc = str(item.get("description") or "").rstrip(". ")
            item["description"] = f"{desc}. {' '.join(extras)}." if desc else f"{' '.join(extras)}."
        result.append(item)
    return result


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------

def _combined_text(requirements: list[dict[str, Any]], architecture_config: dict[str, Any], lowercase: bool = True) -> str:
    values: list[str] = []
    for key in [
        "architecture_input_text",
        "network_name",
        "network_purpose",
        "network_description",
        "middleware_stack",
        "mid_stack",
        "firewall_setting",
        "auth_method",
        "hardware_spec",
        "hard_spec",
        "description_note",
    ]:
        value = architecture_config.get(key)
        if value:
            values.append(str(value))
    values.append(str(requirements))
    text = " | ".join(values)
    return text.lower() if lowercase else text


def _config_text(architecture_config: dict[str, Any]) -> str:
    return " | ".join(str(v) for v in architecture_config.values() if v is not None)


def _contains_any(text: str, keywords: list[str]) -> bool:
    lower = str(text).lower()
    for keyword in keywords:
        kw = str(keyword).lower().strip()
        if not kw:
            continue
        # 영어/숫자 키워드는 단어 일부(storage 안의 rag, mail 안의 ai 등) 오탐을 막습니다.
        if re.fullmatch(r"[a-z0-9_.+/# -]+", kw):
            if _keyword_matches(lower, kw):
                return True
        elif kw in lower:
            return True
    return False


def _ends_with_any(text: str, suffixes: list[str]) -> bool:
    return any(text.rstrip().endswith(suffix) for suffix in suffixes)


def _join_techs(techs: list[str]) -> str:
    return "/".join(_unique_strings(techs))


def _display_token(token: str) -> str:
    text = " ".join(str(token).strip().split())
    if not text:
        return ""
    replacements = {
        "api": "API",
        "db": "DB",
        "rdbms": "RDBMS",
        "nosql": "NoSQL",
        "sso": "SSO",
        "oauth": "OAuth",
        "oauth2": "OAuth2",
        "oidc": "OIDC",
        "jwt": "JWT",
        "llm": "LLM",
        "vlm": "VLM",
        "sllm": "SLLM",
        "rag": "RAG",
        "ai": "AI",
        "was": "WAS",
        "nas": "NAS",
        "nfs": "NFS",
        "rds": "RDS",
        "s3": "S3",
        "gcs": "GCS",
        "obs": "OBS",
        "oss": "OSS",
        "mq": "MQ",
        "ci/cd": "CI/CD",
        "cicd": "CI/CD",
        "k8s": "K8s",
        "eks": "EKS",
        "aks": "AKS",
        "gke": "GKE",
        "elk": "ELK",
        "efk": "EFK",
    }
    words = []
    for word in re.split(r"(\s+|/|-)", text):
        lower = word.lower()
        if lower in replacements:
            words.append(replacements[lower])
        else:
            words.append(word)
    result = "".join(words)

    # 완전 소문자로 들어온 기술명은 가독성을 위해 Title 형태로 보정합니다. 이미 대소문자가 섞인 토큰은 보존합니다.
    if result.islower() and len(result) > 3:
        return result.title()
    return result


def _attach_driver_categories(components: list[dict[str, Any]], drivers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    categories = [str(driver.get("category")) for driver in drivers if isinstance(driver, dict) and driver.get("category")]
    return [{**component, "driver_categories": component.get("driver_categories") or categories} for component in components]


def _has_category(text: str, category: str) -> bool:
    aliases = {
        "security": ("security", "보안", "인증", "권한", "암호화", "접근", "api key", "jwt", "sso", "oauth"),
        "performance": ("performance", "성능", "응답", "처리량", "동시", "확장", "cache", "redis", "캐시"),
        "operation": ("operation", "운영", "모니터링", "백업", "로그", "복구", "prometheus", "grafana"),
        "integration": ("integration", "연계", "interface", "인터페이스", "외부", "api", "gateway", "게이트웨이"),
        "deployment": ("deployment", "배포", "서버", "cloud", "클라우드", "망", "네트워크", "방화벽", "rds", "s3", "컨테이너"),
        "data": ("data", "데이터", "db", "file", "파일", "vector", "저장", "database", "스토리지"),
    }
    return any(alias in text for alias in aliases[category])


def _unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        key = text.lower()
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    return result


def _safe_id(value: str) -> str:
    normalized = "".join(char if char.isalnum() else "_" for char in value.upper()).strip("_")
    if normalized and normalized[0].isdigit():
        normalized = "COMP_" + normalized
    return normalized or "COMP"
