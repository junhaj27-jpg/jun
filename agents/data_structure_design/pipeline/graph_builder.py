"""요구사항 기반 ERD 생성 전체 흐름을 연결합니다."""

from typing import Any

from agents.data_structure_design.pipeline.column_designer import design_columns
from agents.data_structure_design.pipeline.domain_classifier import classify_domain
from agents.data_structure_design.pipeline.domain_dictionary import apply_domain_dictionary
from agents.data_structure_design.pipeline.event_extractor import extract_events
from agents.data_structure_design.pipeline.mermaid_generator import build_mermaid_structure
from agents.data_structure_design.pipeline.metadata_enricher import enrich_table_metadata
from agents.data_structure_design.pipeline.normalizer import normalize_requirements
from agents.data_structure_design.pipeline.object_extractor import extract_domain_objects
from agents.data_structure_design.pipeline.relationship_inferer import infer_relationships
from agents.data_structure_design.pipeline.table_candidate_generator import generate_table_candidates
from agents.data_structure_design.pipeline.table_merger import merge_table_candidates
from agents.data_structure_design.pipeline.validator import validate_erd


def build_erd_from_requirements(requirements: list[Any]) -> dict[str, Any]:
    normalized = normalize_requirements(requirements)
    generic_objects = extract_domain_objects(normalized)
    domain_info = classify_domain(normalized)
    domain_objects = [*generic_objects, *apply_domain_dictionary(normalized, domain_info)]
    events = extract_events(normalized)
    candidates = generate_table_candidates(normalized, domain_objects, events)
    merged_candidates = merge_table_candidates(candidates)
    tables = design_columns(merged_candidates)
    relationships = infer_relationships(tables)
    tables = enrich_table_metadata(tables, relationships)
    erd_schema = {"tables": tables, "relationships": relationships}
    validation_result = validate_erd(tables, relationships)
    mermaid_structure = build_mermaid_structure(erd_schema)
    return {
        "domain_info": domain_info,
        "data_structure_intermediate": _intermediate(normalized, domain_objects, events, candidates, domain_info),
        "erd_schema": erd_schema,
        "erd_mermaid_json": mermaid_structure,
        "validation_result": validation_result,
    }


def _intermediate(
    requirements: list[dict[str, Any]],
    domain_objects: list[dict[str, Any]],
    events: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    domain_info: dict[str, Any],
) -> list[dict[str, Any]]:
    objects_by_req: dict[str, list[dict[str, Any]]] = {}
    events_by_req: dict[str, dict[str, Any]] = {}
    candidates_by_req: dict[str, list[dict[str, Any]]] = {}
    for item in domain_objects:
        objects_by_req.setdefault(item["requirement_id"], []).append(
            {
                "name": item["name"],
                "object_type": item["object_type"],
                "reason": item["reason"],
            }
        )
    for item in events:
        events_by_req[item["requirement_id"]] = item
    for candidate in candidates:
        for requirement_id in candidate.get("source_requirement_ids", []):
            candidates_by_req.setdefault(str(requirement_id), []).append(
                {
                    "table_name": candidate["table_name"],
                    "table_type": candidate["table_type"],
                    "reason": candidate["reason"],
                }
            )
    return [
        {
            "requirement_id": requirement["requirement_id"],
            "requirement_type": requirement["requirement_type"],
            "requirement_name": requirement["requirement_name"],
            "domain": domain_info.get("primary_domain", "GENERAL"),
            "domain_objects": objects_by_req.get(requirement["requirement_id"], []),
            "business_events": events_by_req.get(requirement["requirement_id"], {}).get("business_events", []),
            "status_candidates": events_by_req.get(requirement["requirement_id"], {}).get("status_candidates", []),
            "table_candidates": candidates_by_req.get(requirement["requirement_id"], []),
        }
        for requirement in requirements
    ]
