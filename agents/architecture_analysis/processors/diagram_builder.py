# 아키텍처 다이어그램(Mermaid) 생성 전용 유틸리티입니다.
#
# READABILITY-LAYOUT v6 목적:
# - 선 꼬임을 줄이는 것뿐 아니라, 아키텍처 경계/범위가 자연스럽게 보이도록 배치합니다.
# - 외부/사용자 영역 → 내부 보안/업무 처리 경계 → 후방 리소스 계층 순서로 좌→우 배치합니다.
# - 진입/보안 계층과 애플리케이션/워크플로우 계층은 같은 내부 보안 경계 안에 둡니다.
# - DB/S3/Redis/Qdrant/LLM/모니터링 등으로 직접 fan-out하지 않고 도메인 허브를 통해 연결합니다.
# - 중첩 subgraph 제목이 겹치지 않도록 상위 컨테이너 제목은 숨기고 실제 계층 제목만 노출합니다.
# - 글씨 크기를 키우고 노드 라벨 줄바꿈을 강화해 DOCX 삽입 시 가독성을 높입니다.

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


DEFAULT_DIRECTION = "LR"
DEFAULT_EDGE_LABEL_MODE = "none"  # "none" | "protocol" | "description"
DEFAULT_MAX_TARGETS_PER_GROUP = 5

ROLE_ORDER = {
    "actor": 10,
    "portal": 15,
    "external": 18,
    "gateway": 20,
    "security": 25,
    "api": 30,
    "app": 35,
    "workflow": 40,
    "queue": 45,
    "ai_model": 50,
    "vector": 55,
    "search": 56,
    "data": 60,
    "cache": 61,
    "storage": 62,
    "ops": 80,
    "other": 999,
}

STRONG_ROLE_ALIASES = {
    "portal": ["portal", "포털", "web ui", "웹 ui", "frontend", "front-end", "프론트", "화면", "web app", "웹앱", "dashboard", "대시보드"],
    "gateway": ["gateway", "nginx", "apache", "reverse", "proxy", "lb", "load balancer", "api gateway", "waf", "방화벽", "ingress"],
    "security": ["auth", "oauth", "oidc", "sso", "인증", "인가", "권한", "iam", "keycloak", "security", "보안"],
    "api": ["api server", "api 서버", "api service", "api 서비스", "fastapi", "spring", "django", "tomcat", "was", "web server", "업무 api", "backend", "백엔드", "express"],
    "workflow": ["workflow", "langgraph", "orchestr", "worker", "batch", "scheduler", "job", "작업", "워크플로우", "에이전트", "agent", "processor"],
    "queue": ["kafka", "rabbitmq", "message", "queue", "broker", "event", "이벤트", "브로커", "메시지", "큐"],
    "ai_model": ["llm", "ai service", "ai/llm", "model server", "모델 서버", "모델", "생성형", "추론", "openai", "vllm"],
    "vector": ["qdrant", "vector", "embedding", "임베딩", "벡터", "milvus", "faiss", "pinecone"],
    "search": ["search", "elasticsearch", "opensearch", "검색 엔진", "검색"],
    "cache": ["redis", "cache", "캐시", "session", "세션"],
    "storage": ["s3", "storage", "file", "파일", "bucket", "오브젝트", "object", "blob", "nas", "nfs", "minio"],
    "data": ["db", "database", "mysql", "postgres", "postgresql", "oracle", "mariadb", "rds", "데이터베이스", "dbms"],
    "external": ["external", "외부", "연계", "interface", "인터페이스", "legacy", "레거시", "third party", "3rd"],
    "ops": ["monitor", "grafana", "prometheus", "log", "logging", "모니터링", "로그", "운영", "alert", "알림", "관제", "apm", "backup", "restore", "백업", "복구"],
    "actor": ["user", "client", "사용자", "클라이언트", "브라우저", "민원인", "관리자"],
}

WEAK_DESCRIPTION_ALIASES = {
    "gateway": ["요청을 수신", "라우팅", "프록시", "https 수신"],
    "security": ["인증", "인가", "권한", "토큰", "접근 제어"],
    "api": ["업무 api", "요청 처리", "상태 조회"],
    "workflow": ["오케스트레이션", "워크플로우", "작업 처리", "산출물 생성 흐름", "비동기"],
    "queue": ["메시지", "이벤트", "비동기", "큐"],
    "ai_model": ["llm", "모델 추론", "생성형 ai"],
    "vector": ["벡터", "임베딩", "rag"],
    "search": ["검색"],
    "cache": ["캐시", "세션"],
    "storage": ["파일", "오브젝트", "업로드", "다운로드", "산출물 저장"],
    "data": ["데이터 저장", "메타데이터", "이력", "db"],
    "external": ["외부 시스템", "외부 api", "연계"],
    "ops": ["모니터링", "로그", "관제", "알림"],
}

PRIORITY_KEYWORDS = [
    "request", "요청", "https", "http", "api", "auth", "인증", "권한",
    "workflow", "워크플로우", "orchestration", "agent", "에이전트",
    "sql", "db", "저장", "조회", "file", "s3", "vector", "rag", "검색",
    "cache", "redis", "queue", "event", "monitor", "log", "연계", "외부",
]


class _DiagramContext:
    def __init__(self, components: list[dict[str, Any]]) -> None:
        self.components = components
        self.cid_to_component: dict[str, dict[str, Any]] = {}
        self.alias_to_cid: dict[str, str] = {}
        self.cid_to_safe: dict[str, str] = {}
        self.role_to_cids: dict[str, list[str]] = defaultdict(list)

        for index, component in enumerate(components, start=1):
            cid = _component_id(component, index)
            self.cid_to_component[cid] = component
            self.cid_to_safe[cid] = _safe_mermaid_id(cid)

            role = _component_role(component)
            self.role_to_cids[role].append(cid)

            for alias in _component_aliases(component, cid):
                self.alias_to_cid[_norm(alias)] = cid

    def resolve(self, value: Any) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        if raw in self.cid_to_component:
            return raw
        return self.alias_to_cid.get(_norm(raw), raw)

    def safe(self, cid: str) -> str:
        return self.cid_to_safe.get(cid, _safe_mermaid_id(cid))

    def role(self, cid: str) -> str:
        return _component_role(self.cid_to_component.get(cid))

    def component(self, cid: str) -> dict[str, Any] | None:
        return self.cid_to_component.get(cid)

    def cids_by_roles(self, *roles: str) -> list[str]:
        result: list[str] = []
        for role in roles:
            result.extend(self.role_to_cids.get(role, []))
        return result


# architecture_builder.py가 호출하는 공개 함수입니다.
def build_clean_architecture_mermaid_source(
    structure: dict[str, Any],
    *,
    direction: str = DEFAULT_DIRECTION,
    edge_label_mode: str = DEFAULT_EDGE_LABEL_MODE,
    max_edges: int = 16,
) -> str:
    """범위/경계 개념을 살린 compact Mermaid flowchart를 생성합니다."""

    components = [c for c in structure.get("components") or [] if isinstance(c, dict)]
    relations = [r for r in (structure.get("relations") or structure.get("edges") or []) if isinstance(r, dict)]
    ctx = _DiagramContext(components)

    direction = (direction or DEFAULT_DIRECTION).upper()
    if direction not in {"TB", "TD", "LR", "RL", "BT"}:
        direction = DEFAULT_DIRECTION

    lines: list[str] = [
        '%%{init: {"theme": "base", "themeVariables": {"fontFamily": "Malgun Gothic, NanumGothic, Arial, sans-serif", "fontSize": "28px", "primaryTextColor": "#111827", "lineColor": "#64748B"}, "themeCSS": ".nodeLabel, .edgeLabel { font-size: 27px !important; } .cluster-label, .cluster-label span, .cluster-label foreignObject div { font-size: 26px !important; font-weight: 700 !important; } .node rect, .node polygon, .node ellipse { stroke-width: 1.6px !important; }", "flowchart": {"curve": "basis", "nodeSpacing": 48, "rankSpacing": 64, "padding": 34, "htmlLabels": true}} }%%',
        f"flowchart {direction}",
        "",
    ]

    declared_hubs: set[str] = set()
    virtual_nodes: set[str] = set()
    _emit_compact_semantic_nodes(lines, ctx, declared_hubs, virtual_nodes)

    planned_edges = _plan_compact_edges(
        ctx,
        relations,
        declared_hubs=declared_hubs,
        virtual_nodes=virtual_nodes,
        max_targets_per_group=max(DEFAULT_MAX_TARGETS_PER_GROUP, max_edges // 3),
    )

    if planned_edges:
        lines.append("  %% 핵심 업무 흐름 및 계층 간 연결")

    for source, target, label in planned_edges:
        if not source or not target or source == target:
            continue
        label = _short_edge_label(label, edge_label_mode)
        if label:
            lines.append(f'  {source} -->|"{_escape_mermaid(label)}"| {target}')
        else:
            lines.append(f"  {source} --> {target}")

    lines.extend(_mermaid_styles())
    for hub_id in sorted(declared_hubs):
        lines.append(f"  class {hub_id} hub;")
    for virtual_id in sorted(virtual_nodes):
        lines.append(f"  class {virtual_id} virtual;")
    return "\n".join(lines).rstrip() + "\n"


# 테스트 렌더러의 Graphviz fallback에서 사용하는 공개 함수입니다.
def select_diagram_relations(
    relations: list[dict[str, Any]],
    *,
    components: list[dict[str, Any]] | None = None,
    max_edges: int = 16,
) -> list[dict[str, Any]]:
    """그림용 핵심 relation만 반환합니다."""
    components = components or []
    ctx = _DiagramContext([c for c in components if isinstance(c, dict)])
    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def resolved_pair(rel: dict[str, Any]) -> tuple[str, str]:
        source = ctx.resolve(_relation_source(rel)) if components else _relation_source(rel)
        target = ctx.resolve(_relation_target(rel)) if components else _relation_target(rel)
        return source, target

    for rel in sorted([r for r in relations if isinstance(r, dict)], key=_relation_score, reverse=True):
        source, target = resolved_pair(rel)
        if not source or not target or source == target:
            continue
        pair = (source, target)
        if pair in seen:
            continue
        seen.add(pair)
        selected.append(rel)
        if len(selected) >= max_edges:
            break

    return selected


def _emit_compact_semantic_nodes(
    lines: list[str],
    ctx: _DiagramContext,
    declared_hubs: set[str],
    virtual_nodes: set[str],
) -> None:
    emitted: set[str] = set()

    def emit_nodes(cids: list[str], indent: str = "    ") -> None:
        for cid in cids:
            if cid not in ctx.cid_to_component:
                continue
            component = ctx.component(cid) or {}
            lines.append(f'{indent}{ctx.safe(cid)}["{_escape_mermaid(_component_label(component))}"]')
            emitted.add(cid)

    actors = ctx.cids_by_roles("actor")
    portals = ctx.cids_by_roles("portal")
    external_nodes = ctx.cids_by_roles("external")
    gateways = ctx.cids_by_roles("gateway")
    security_nodes = ctx.cids_by_roles("security")
    app_nodes = ctx.cids_by_roles("api", "app")
    workflow_nodes = ctx.cids_by_roles("workflow")
    queue_nodes = ctx.cids_by_roles("queue")
    ai_nodes = ctx.cids_by_roles("ai_model", "vector", "search")
    data_nodes = ctx.cids_by_roles("data", "cache", "storage")
    ops_nodes = ctx.cids_by_roles("ops")
    other_nodes = ctx.cids_by_roles("other")

    # 1) 시스템 바깥 영역: 실제 사용자가 없더라도 업무 흐름의 시작점을 명확히 보이도록 가상 사용자 노드를 추가합니다.
    lines.append('  subgraph OUTER_BOUNDARY["외부/사용자"]')
    lines.append("    direction TB")
    if actors:
        emit_nodes(actors, "    ")
    else:
        virtual_nodes.add("DIAGRAM_USER")
        lines.append('    DIAGRAM_USER["사용자/<br/>클라이언트"]')
    emit_nodes(portals, "    ")
    if external_nodes:
        lines.append('    subgraph EXT_BOUNDARY["외부 연계 대상"]')
        lines.append("      direction TB")
        emit_nodes(external_nodes, "      ")
        lines.append("    end")
    lines.append("  end")
    lines.append("")

    # 2) 내부 시스템 경계: 진입/보안과 애플리케이션을 같은 내부 보안 경계 안에 좌→우로 배치합니다.
    lines.append('  subgraph SYSTEM_BOUNDARY[" "]')
    lines.append("    direction LR")

    lines.append('    subgraph SEC_APP_BOUNDARY[" "]')
    lines.append("      direction LR")

    lines.append('      subgraph ENTRY_BOUNDARY["진입/보안"]')
    lines.append("        direction TB")
    emit_nodes(gateways, "        ")
    emit_nodes(security_nodes, "        ")
    lines.append("      end")

    lines.append('      subgraph APP_BOUNDARY["애플리케이션/워크플로우"]')
    lines.append("        direction TB")
    emit_nodes(app_nodes, "        ")
    emit_nodes(workflow_nodes, "        ")
    emit_nodes(queue_nodes, "        ")
    lines.append("      end")
    lines.append("    end")

    # 3) 후방 리소스 영역: 여러 저장소/AI/운영 선은 허브로 모아 짧게 분기합니다.
    if ai_nodes or data_nodes or ops_nodes or other_nodes:
        lines.append('    subgraph RESOURCE_BOUNDARY[" "]')
        lines.append("      direction TB")

        if data_nodes:
            lines.append('      subgraph DATA_BOUNDARY["데이터/저장소"]')
            lines.append("        direction LR")
            _declare_hub(lines, declared_hubs, "DIAGRAM_DATA_HUB", "데이터 접근", "        ")
            emit_nodes(data_nodes, "        ")
            lines.append("      end")

        if ai_nodes:
            lines.append('      subgraph AI_BOUNDARY["AI/RAG"]')
            lines.append("        direction LR")
            _declare_hub(lines, declared_hubs, "DIAGRAM_AI_HUB", "AI/RAG 연계", "        ")
            emit_nodes(ai_nodes, "        ")
            lines.append("      end")

        if ops_nodes:
            lines.append('      subgraph OPS_BOUNDARY["운영/관제"]')
            lines.append("        direction LR")
            _declare_hub(lines, declared_hubs, "DIAGRAM_OPS_HUB", "운영/모니터링", "        ")
            emit_nodes(ops_nodes, "        ")
            lines.append("      end")

        if other_nodes:
            lines.append('      subgraph ETC_BOUNDARY["기타"]')
            lines.append("        direction TB")
            emit_nodes(other_nodes, "        ")
            lines.append("      end")

        lines.append("    end")

    # 혹시 어떤 역할에서도 방출되지 않은 노드가 있으면 내부 기타 영역에 안전하게 배치합니다.
    rest = [cid for cid in ctx.cid_to_component if cid not in emitted]
    if rest:
        lines.append('    subgraph REST_BOUNDARY["미분류"]')
        lines.append("      direction TB")
        emit_nodes(rest, "      ")
        lines.append("    end")

    lines.append("  end")
    lines.append("")


def _declare_hub(lines: list[str], declared_hubs: set[str], hub_id: str, label: str, indent: str) -> None:
    if hub_id in declared_hubs:
        return
    declared_hubs.add(hub_id)
    lines.append(f'{indent}{hub_id}(["{_escape_mermaid(label)}"])')


def _plan_compact_edges(
    ctx: _DiagramContext,
    relations: list[dict[str, Any]],
    *,
    declared_hubs: set[str],
    virtual_nodes: set[str],
    max_targets_per_group: int,
) -> list[tuple[str, str, str]]:
    edges: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(source_id: str, target_id: str, label: str = "") -> None:
        if not source_id or not target_id or source_id == target_id:
            return
        pair = (source_id, target_id)
        if pair in seen:
            return
        seen.add(pair)
        edges.append((source_id, target_id, label))

    actors = ctx.cids_by_roles("actor")
    portals = ctx.cids_by_roles("portal")
    external_nodes = ctx.cids_by_roles("external")
    gateways = ctx.cids_by_roles("gateway")
    security_nodes = ctx.cids_by_roles("security")
    app_nodes = ctx.cids_by_roles("api", "app")
    workflow_nodes = ctx.cids_by_roles("workflow")
    queue_nodes = ctx.cids_by_roles("queue")
    ai_targets = ctx.cids_by_roles("ai_model", "vector", "search")[:max_targets_per_group]
    data_targets = ctx.cids_by_roles("data", "cache", "storage")[:max_targets_per_group]
    ops_targets = ctx.cids_by_roles("ops")[:max_targets_per_group]

    primary_actor = actors[0] if actors else ("DIAGRAM_USER" if "DIAGRAM_USER" in virtual_nodes else "")
    primary_portal = portals[0] if portals else ""
    primary_gateway = gateways[0] if gateways else ""
    primary_security = security_nodes[0] if security_nodes else ""
    primary_app = app_nodes[0] if app_nodes else ""
    primary_workflow = workflow_nodes[0] if workflow_nodes else ""
    primary_queue = queue_nodes[0] if queue_nodes else ""

    # 외부/사용자 → 포털 → 게이트웨이 → 인증/보안 → 업무 API → 워크플로우/큐 순서의 주 흐름입니다.
    if primary_actor and primary_portal:
        add(_safe_for(ctx, primary_actor), ctx.safe(primary_portal))
    entry_source = primary_portal or primary_actor

    if entry_source and primary_gateway:
        add(_safe_for(ctx, entry_source), ctx.safe(primary_gateway))
    elif entry_source and primary_app:
        add(_safe_for(ctx, entry_source), ctx.safe(primary_app))

    if primary_gateway and primary_security:
        add(ctx.safe(primary_gateway), ctx.safe(primary_security))
    boundary_source = primary_security or primary_gateway

    if boundary_source and primary_app:
        add(ctx.safe(boundary_source), ctx.safe(primary_app))
    elif boundary_source and primary_workflow:
        add(ctx.safe(boundary_source), ctx.safe(primary_workflow))

    if primary_app and primary_workflow:
        add(ctx.safe(primary_app), ctx.safe(primary_workflow))

    if primary_workflow and primary_queue:
        add(ctx.safe(primary_workflow), ctx.safe(primary_queue))
    elif primary_app and primary_queue:
        add(ctx.safe(primary_app), ctx.safe(primary_queue))

    # 같은 역할 컴포넌트가 여러 개이면 mesh가 아니라 짧은 체인으로만 보조 연결합니다.
    for group in [portals, gateways, security_nodes, app_nodes, workflow_nodes, queue_nodes]:
        for left, right in zip(group, group[1:]):
            add(ctx.safe(left), ctx.safe(right))

    backend_source = primary_queue or primary_workflow or primary_app or boundary_source or primary_gateway or entry_source

    # 외부 시스템은 원칙적으로 시스템 바깥입니다. 외부 데이터 제공 API는 gateway/queue 쪽으로 들어오도록 짧게 연결합니다.
    for ext in external_nodes[:max_targets_per_group]:
        if primary_gateway:
            add(ctx.safe(ext), ctx.safe(primary_gateway))
        elif primary_queue:
            add(ctx.safe(ext), ctx.safe(primary_queue))
        elif primary_app:
            add(ctx.safe(ext), ctx.safe(primary_app))

    # 후방 리소스는 허브로만 연결해 fan-out 선 중복을 줄입니다.
    if backend_source and data_targets and "DIAGRAM_DATA_HUB" in declared_hubs:
        add(_safe_for(ctx, backend_source), "DIAGRAM_DATA_HUB")
        for target in data_targets:
            add("DIAGRAM_DATA_HUB", ctx.safe(target))

    if backend_source and ai_targets and "DIAGRAM_AI_HUB" in declared_hubs:
        add(_safe_for(ctx, backend_source), "DIAGRAM_AI_HUB")
        for target in ai_targets:
            add("DIAGRAM_AI_HUB", ctx.safe(target))

    if backend_source and ops_targets and "DIAGRAM_OPS_HUB" in declared_hubs:
        add(_safe_for(ctx, backend_source), "DIAGRAM_OPS_HUB")
        for target in ops_targets:
            add("DIAGRAM_OPS_HUB", ctx.safe(target))

    # 특이 구조이거나 role 분류가 안 되는 경우 최소 연결을 보정합니다.
    if not edges:
        ordered = sorted(ctx.cid_to_component.keys(), key=lambda cid: (ROLE_ORDER.get(ctx.role(cid), 999), cid))
        for source, target in zip(ordered, ordered[1:]):
            add(ctx.safe(source), ctx.safe(target))
            if len(edges) >= 8:
                break

    return edges


def _safe_for(ctx: _DiagramContext, cid_or_virtual: str) -> str:
    if cid_or_virtual.startswith("DIAGRAM_"):
        return cid_or_virtual
    return ctx.safe(cid_or_virtual)


def _relation_score(relation: dict[str, Any] | None) -> int:
    if not relation:
        return 0
    text = " ".join(
        str(relation.get(key) or "")
        for key in ["description", "label", "protocol", "type", "relation_type", "data_flow", "purpose"]
    ).lower()
    return sum(5 for keyword in PRIORITY_KEYWORDS if keyword.lower() in text)


def _component_role(component: dict[str, Any] | None) -> str:
    if not component:
        return "other"

    # id/name/type을 layer보다 먼저 판단합니다.
    # 예: layer가 Agent Orchestration이어도 "모니터링", "백업"은 운영/관제 계층이어야 합니다.
    identity_text = " ".join(
        str(component.get(key) or "")
        for key in ["component_id", "id", "name", "component_name", "type"]
    ).lower()
    layer_text = str(component.get("layer") or "").lower()
    desc_text = str(component.get("description") or "").lower()

    identity_order = [
        "portal", "gateway", "security", "ops", "queue", "ai_model", "vector", "search",
        "cache", "storage", "data", "external", "api", "workflow", "actor",
    ]
    for role in identity_order:
        aliases = STRONG_ROLE_ALIASES.get(role, [])
        if any(alias.lower() in identity_text for alias in aliases):
            return role

    # description은 actor 판단에 사용하지 않습니다.
    desc_order = [
        "gateway", "security", "ops", "queue", "ai_model", "vector", "search",
        "cache", "storage", "data", "external", "api", "workflow",
    ]
    for role in desc_order:
        aliases = WEAK_DESCRIPTION_ALIASES.get(role, [])
        if any(alias.lower() in desc_text for alias in aliases):
            return role

    # 마지막으로 layer를 보조 판단합니다. layer는 넓은 영역명이라 오분류 가능성이 높기 때문입니다.
    layer_order = [
        "portal", "gateway", "security", "ops", "queue", "ai_model", "vector", "search",
        "cache", "storage", "data", "external", "api", "workflow",
    ]
    for role in layer_order:
        aliases = STRONG_ROLE_ALIASES.get(role, [])
        if any(alias.lower() in layer_text for alias in aliases):
            return role

    return "other"


def _component_id(component: dict[str, Any], index: int) -> str:
    return str(component.get("component_id") or component.get("id") or component.get("name") or f"COMP-{index:03d}")


def _component_aliases(component: dict[str, Any], cid: str) -> list[str]:
    aliases = [cid]
    for key in ["component_id", "id", "name", "component_name"]:
        value = component.get(key)
        if value:
            aliases.append(str(value))
    return aliases


def _component_label(component: dict[str, Any]) -> str:
    label = _first(component.get("name"), component.get("component_name"), component.get("component_id"), "Component")
    return _wrap_label(label, max_line_chars=10)


def _wrap_label(text: Any, max_line_chars: int = 13) -> str:
    """Mermaid htmlLabels용 간단 줄바꿈. 캔버스 폭을 줄이고 글씨 가독성을 높입니다."""
    s = re.sub(r"\s+", " ", str(text or "").strip())
    if len(s) <= max_line_chars:
        return s

    # slash, 괄호, 공백, 하이픈 근처를 우선으로 줄바꿈합니다.
    s = s.replace("/", "/<br/>").replace("·", "·<br/>")
    if "<br/>" in s:
        return s

    tokens = s.split(" ")
    if len(tokens) > 1:
        lines: list[str] = []
        cur = ""
        for token in tokens:
            if cur and len(cur) + 1 + len(token) > max_line_chars:
                lines.append(cur)
                cur = token
            else:
                cur = token if not cur else cur + " " + token
        if cur:
            lines.append(cur)
        return "<br/>".join(lines)

    # 공백 없는 한글/영문 혼합명은 길이 기준으로 한 번만 끊습니다.
    parts = [s[i : i + max_line_chars] for i in range(0, len(s), max_line_chars)]
    return "<br/>".join(parts[:3])


def _relation_source(relation: dict[str, Any]) -> str:
    return str(relation.get("source") or relation.get("from") or relation.get("source_component_id") or "")


def _relation_target(relation: dict[str, Any]) -> str:
    return str(relation.get("target") or relation.get("to") or relation.get("target_component_id") or "")


def _short_edge_label(label: Any, mode: str) -> str:
    mode = (mode or "none").lower()
    if mode == "none":
        return ""
    value = str(label or "").strip()
    if not value:
        return ""
    return value if len(value) <= 10 else value[:9].rstrip() + "…"


def _mermaid_styles() -> list[str]:
    return [
        "",
        "  classDef default fill:#F2F4FF,stroke:#8A8FBF,color:#111827,font-size:27px;",
        "  classDef hub fill:#FFF7ED,stroke:#F97316,color:#111827,stroke-width:2.0px,font-size:27px;",
        "  classDef virtual fill:#ECFEFF,stroke:#0891B2,color:#111827,stroke-width:1.8px,font-size:27px;",
        "  classDef boundary fill:#FEFCE8,stroke:#D9E18C,color:#374151,font-size:26px;",
        "  linkStyle default stroke:#64748B,stroke-width:1.7px;",
    ]


def _safe_mermaid_id(value: Any) -> str:
    text = str(value or "NODE")
    node = re.sub(r"[^0-9A-Za-z_]+", "_", text.upper()).strip("_")
    if not node:
        node = "NODE"
    if node[0].isdigit():
        node = "N_" + node
    return node


def _escape_mermaid(text: Any) -> str:
    # <br/>은 htmlLabels 줄바꿈 용도로 살려둡니다.
    return str(text or "").replace('"', "'").replace("|", "/").replace("\n", " ")


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _first(*values: Any) -> str:
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""
