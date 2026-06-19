# 아키텍처 구조를 Mermaid 코드로 생성합니다.

import re
from typing import Any


def build_architecture_mermaid(structure: dict[str, Any]) -> str:
    components = structure.get("components") or []
    relations = structure.get("relations") or structure.get("relationships") or []
    layers = structure.get("layers") or []
    component_map = {_component_id(component, index): component for index, component in enumerate(components)}
    original_to_node = {
        str(component.get("component_id") or component.get("id") or component.get("name") or node_id): node_id
        for node_id, component in component_map.items()
    }
    lines = ["flowchart TD"]
    grouped: set[str] = set()
    for layer_index, layer in enumerate(layers):
        layer_name = str(layer.get("name") or layer.get("layer_name") or f"Layer {layer_index + 1}") if isinstance(layer, dict) else str(layer)
        layer_components = _layer_component_refs(layer) if isinstance(layer, dict) else []
        lines.append(f"    subgraph {_node_id(layer_name)}[{_escape_label(layer_name)}]")
        lines.append("        direction TB")
        for component_ref in layer_components:
            raw_component_id = str(component_ref if not isinstance(component_ref, dict) else component_ref.get("component_id") or component_ref.get("id") or component_ref.get("name"))
            component_id = original_to_node.get(raw_component_id) or _node_id(raw_component_id)
            component = component_map.get(component_id, component_ref if isinstance(component_ref, dict) else {})
            lines.append(f"        {component_id}[{_escape_label(_label(component, component_id))}]")
            grouped.add(component_id)
        lines.append("    end")
    for component_id, component in component_map.items():
        if component_id not in grouped:
            lines.append(f"    {component_id}[{_escape_label(_label(component, component_id))}]")
    for relation in relations:
        raw_source = str(relation.get("source") or relation.get("from") or relation.get("source_component_id") or "")
        raw_target = str(relation.get("target") or relation.get("to") or relation.get("target_component_id") or "")
        source = original_to_node.get(raw_source) or _node_id(raw_source)
        target = original_to_node.get(raw_target) or _node_id(raw_target)
        if source and target:
            label = relation.get("description") or relation.get("label")
            if label:
                lines.append(f"    {source} -->|{_escape_label(str(label))}| {target}")
            else:
                lines.append(f"    {source} --> {target}")
    return "\n".join(lines)


def _component_id(component: dict[str, Any], index: int) -> str:
    return _node_id(str(component.get("component_id") or component.get("id") or component.get("name") or f"COMP_{index + 1}"))


def _label(component: dict[str, Any], fallback: str) -> str:
    return str(component.get("name") or component.get("label") or fallback)


def _node_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", value).strip("_") or "NODE"


def _layer_component_refs(layer: dict[str, Any]) -> list[Any]:
    refs = layer.get("components")
    if isinstance(refs, list):
        return refs
    refs = layer.get("component_ids")
    return refs if isinstance(refs, list) else []


def _escape_label(value: str) -> str:
    return (
        value.replace("[", "")
        .replace("]", "")
        .replace("|", "/")
        .replace("(", "")
        .replace(")", "")
        .replace('"', "")
        .replace("'", "")
    )
