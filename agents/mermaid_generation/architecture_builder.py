# 아키텍처 구조를 Mermaid 코드로 생성합니다.

import re
from typing import Any


def build_architecture_mermaid(structure: dict[str, Any]) -> str:
    components = structure.get("components") or []
    relations = structure.get("relations") or structure.get("relationships") or []
    layers = structure.get("layers") or []
    component_map = {_component_id(component, index): component for index, component in enumerate(components)}
    lines = ["flowchart TD"]
    grouped: set[str] = set()
    for layer_index, layer in enumerate(layers):
        layer_name = str(layer.get("name") or layer.get("layer_name") or f"Layer {layer_index + 1}") if isinstance(layer, dict) else str(layer)
        layer_components = layer.get("components", []) if isinstance(layer, dict) else []
        lines.append(f"    subgraph {_node_id(layer_name)}[{layer_name}]")
        for component_ref in layer_components:
            component_id = str(component_ref if not isinstance(component_ref, dict) else component_ref.get("component_id") or component_ref.get("id"))
            component = component_map.get(component_id, component_ref if isinstance(component_ref, dict) else {})
            lines.append(f"        {component_id}[{_label(component, component_id)}]")
            grouped.add(component_id)
        lines.append("    end")
    for component_id, component in component_map.items():
        if component_id not in grouped:
            lines.append(f"    {component_id}[{_label(component, component_id)}]")
    for relation in relations:
        source = relation.get("source") or relation.get("from") or relation.get("source_component_id")
        target = relation.get("target") or relation.get("to") or relation.get("target_component_id")
        if source and target:
            lines.append(f"    {source} --> {target}")
    return "\n".join(lines)


def _component_id(component: dict[str, Any], index: int) -> str:
    return str(component.get("component_id") or component.get("id") or _node_id(str(component.get("name") or f"COMP_{index + 1}")))


def _label(component: dict[str, Any], fallback: str) -> str:
    return str(component.get("name") or component.get("label") or fallback)


def _node_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", value).strip("_") or "NODE"
