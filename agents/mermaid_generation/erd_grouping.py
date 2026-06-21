"""ERD Mermaid 입력 구조를 관계 상세/단독 엔티티 그룹으로 분리합니다."""

from collections import defaultdict
from typing import Any

import networkx as nx


DEFAULT_MAX_TABLES_PER_GROUP = 6
RECOMMENDED_TABLES_PER_GROUP = 6
ORPHAN_TABLES_PER_GROUP = 4


def split_erd_structure(
    structure: dict[str, Any],
    *,
    max_tables_per_group: int = DEFAULT_MAX_TABLES_PER_GROUP,
) -> list[dict[str, Any]]:
    """통합 ERD 없이 관계 그룹과 단독 엔티티 그룹만 반환합니다."""

    entities = _entities(structure)
    relationships = _relationships(structure)
    entity_by_name = {_entity_name(entity): entity for entity in entities if _entity_name(entity)}
    if not entity_by_name:
        return []

    detail_groups = _detail_groups(entity_by_name, relationships, max_tables_per_group)
    detail_group_objects = [
        _build_group(
            index,
            table_names,
            entity_by_name,
            relationships,
            group_id=f"ERD-GROUP-{index:03d}",
            group_type="detail",
        )
        for index, table_names in enumerate(detail_groups, start=1)
        if table_names
    ]
    orphan_group_objects = _orphan_groups(
        entity_by_name,
        relationships,
        detail_group_objects,
        start_index=len(detail_group_objects) + 1,
    )
    groups = [*detail_group_objects, *orphan_group_objects]
    return _ensure_all_tables_rendered(groups, entity_by_name, relationships)


def _detail_groups(
    entity_by_name: dict[str, dict[str, Any]],
    relationships: list[dict[str, Any]],
    max_tables_per_group: int,
) -> list[list[str]]:
    graph = nx.Graph()
    graph.add_nodes_from(entity_by_name)
    for relation in relationships:
        parent = _relation_parent(relation)
        child = _relation_child(relation)
        if parent in entity_by_name and child in entity_by_name:
            graph.add_edge(parent, child)
    groups: list[list[str]] = []
    for component in nx.connected_components(graph):
        if not _component_has_relationship(component, graph):
            continue
        component_entities = [entity_by_name[name] for name in component]
        groups.extend(_split_large_component(component_entities, relationships, max_tables_per_group))
    return _merge_small_groups(groups, entity_by_name, max_tables_per_group)


def _split_large_component(
    entities: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    max_tables: int,
) -> list[list[str]]:
    names = [_entity_name(entity) for entity in entities if _entity_name(entity)]
    if len(names) <= max_tables:
        return [_sort_names(names, entities)]

    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entity in entities:
        by_domain[_group_key(entity)].append(entity)

    domain_groups: list[list[str]] = []
    for domain_entities in by_domain.values():
        if len(domain_entities) <= max_tables:
            domain_groups.append(_sort_names([_entity_name(item) for item in domain_entities], domain_entities))
            continue
        domain_groups.extend(_chunk_by_importance(domain_entities, max_tables))

    # 관계 설명을 위해 다른 도메인의 테이블을 보조 삽입하면 같은 테이블이
    # 여러 ERD 이미지에 반복 등장한다. 각 테이블은 대표 그룹에만 배치하고,
    # 교차 도메인 관계는 상세 명세/관계 목록에서 보완한다.
    return domain_groups


def _chunk_by_importance(entities: list[dict[str, Any]], max_tables: int) -> list[list[str]]:
    ordered = sorted(
        entities,
        key=lambda item: (
            int(item.get("importance_score") or 0),
            int(item.get("relation_count") or 0),
            _entity_name(item),
        ),
        reverse=True,
    )
    chunk_size = min(max_tables, RECOMMENDED_TABLES_PER_GROUP)
    return [
        [_entity_name(item) for item in ordered[index : index + chunk_size] if _entity_name(item)]
        for index in range(0, len(ordered), chunk_size)
    ]


def _build_group(
    index: int,
    table_names: list[str],
    entity_by_name: dict[str, dict[str, Any]],
    relationships: list[dict[str, Any]],
    *,
    group_id: str | None = None,
    group_name: str | None = None,
    group_type: str = "detail",
) -> dict[str, Any]:
    table_names = list(dict.fromkeys(table_names))
    table_set = set(table_names)
    entities = [entity_by_name[name] for name in table_names if name in entity_by_name]
    group_relationships = [
        relation
        for relation in relationships
        if _relation_parent(relation) in table_set and _relation_child(relation) in table_set
    ]
    domain_groups = sorted({_group_key(entity) for entity in entities})
    label = group_name or (", ".join(domain_groups) if domain_groups else "COMMON")
    return {
        "group_id": group_id or f"ERD-GROUP-{index:03d}",
        "group_name": label,
        "group_type": group_type,
        "table_names": table_names,
        "tables": entities,
        "entities": entities,
        "relationships": group_relationships,
    }


def _orphan_groups(
    entity_by_name: dict[str, dict[str, Any]],
    relationships: list[dict[str, Any]],
    detail_groups: list[dict[str, Any]],
    *,
    start_index: int,
) -> list[dict[str, Any]]:
    related = _related_table_names(relationships)
    all_names = set(entity_by_name)
    orphan_names = sorted(all_names - related)
    if not orphan_names:
        return []

    groups: list[dict[str, Any]] = []
    group_no = start_index
    by_domain: dict[str, list[str]] = defaultdict(list)
    for name in orphan_names:
        by_domain[_group_key(entity_by_name[name])].append(name)
    for domain in sorted(by_domain):
        names = _sort_names(
            by_domain[domain],
            [entity_by_name[name] for name in by_domain[domain]],
        )
        for chunk_index, chunk in enumerate(_chunks(names, ORPHAN_TABLES_PER_GROUP), start=1):
            groups.append(
                _build_group(
                    group_no,
                    chunk,
                    entity_by_name,
                    relationships,
                    group_id=f"ERD-ORPHAN-{group_no:03d}",
                    group_name=f"{domain} 단독 엔티티 {chunk_index}",
                    group_type="orphan",
                )
            )
            group_no += 1
    return groups


def _ensure_all_tables_rendered(
    groups: list[dict[str, Any]],
    entity_by_name: dict[str, dict[str, Any]],
    relationships: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    all_tables = set(entity_by_name)
    rendered_tables = {
        str(name)
        for group in groups
        for name in group.get("table_names", [])
    }
    missing_tables = sorted(all_tables - rendered_tables)
    if not missing_tables:
        return groups
    extra_groups = []
    for index, chunk in enumerate(_chunks(missing_tables, ORPHAN_TABLES_PER_GROUP), start=1):
        extra_groups.append(
            _build_group(
                len(groups) + index,
                chunk,
                entity_by_name,
                relationships,
                group_id=f"ERD-ORPHAN-MISSING-{index:03d}",
                group_name="ETC 단독 엔티티",
                group_type="orphan",
            )
        )
    return [*groups, *extra_groups]


def _merge_small_groups(
    groups: list[list[str]],
    entity_by_name: dict[str, dict[str, Any]],
    max_tables: int,
) -> list[list[str]]:
    merged: list[list[str]] = []
    for group in sorted(groups, key=lambda item: (-len(item), item)):
        if len(group) >= 3:
            merged.append(group)
            continue
        domain = _group_domain(group, entity_by_name)
        target_index = _find_merge_target(merged, domain, entity_by_name, max_tables, len(group))
        if target_index is None:
            merged.append(group)
        else:
            merged[target_index] = _sort_names(
                list(dict.fromkeys([*merged[target_index], *group])),
                [entity_by_name[name] for name in [*merged[target_index], *group] if name in entity_by_name],
            )
    return merged


def _find_merge_target(
    groups: list[list[str]],
    domain: str,
    entity_by_name: dict[str, dict[str, Any]],
    max_tables: int,
    incoming_size: int,
) -> int | None:
    for index, group in enumerate(groups):
        if len(group) + incoming_size > max_tables:
            continue
        if _group_domain(group, entity_by_name) == domain:
            return index
    for index, group in enumerate(groups):
        if len(group) + incoming_size <= max_tables:
            return index
    return None


def _group_domain(group: list[str], entity_by_name: dict[str, dict[str, Any]]) -> str:
    domains = [
        _group_key(entity_by_name[name])
        for name in group
        if name in entity_by_name
    ]
    return domains[0] if domains else "COMMON"


def _group_key(entity: dict[str, Any]) -> str:
    return str(entity.get("domain_group") or entity.get("table_type") or "COMMON")


def _component_has_relationship(component: set[str], graph: nx.Graph) -> bool:
    return any(graph.degree(node) > 0 for node in component)


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _related_table_names(relationships: list[dict[str, Any]]) -> set[str]:
    related: set[str] = set()
    for relation in relationships:
        parent = _relation_parent(relation)
        child = _relation_child(relation)
        if parent:
            related.add(parent)
        if child:
            related.add(child)
    return related


def _sort_names(names: list[str], entities: list[dict[str, Any]]) -> list[str]:
    entity_by_name = {_entity_name(entity): entity for entity in entities}
    return sorted(
        names,
        key=lambda name: (
            -int(entity_by_name.get(name, {}).get("importance_score") or 0),
            -int(entity_by_name.get(name, {}).get("relation_count") or 0),
            name,
        ),
    )


def _entities(structure: dict[str, Any]) -> list[dict[str, Any]]:
    value = structure.get("entities") or structure.get("tables") or []
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _relationships(structure: dict[str, Any]) -> list[dict[str, Any]]:
    value = structure.get("relationships") or structure.get("relations") or []
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _entity_name(entity: dict[str, Any]) -> str:
    return str(entity.get("table_name") or entity.get("physical_name") or entity.get("name") or "")


def _relation_parent(relation: dict[str, Any]) -> str:
    return str(relation.get("parent_table") or relation.get("to_table") or relation.get("to") or relation.get("target") or "")


def _relation_child(relation: dict[str, Any]) -> str:
    return str(relation.get("child_table") or relation.get("from_table") or relation.get("from") or relation.get("source") or "")
