from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import (
    APPLY_GLOBAL_SCOPE_TO_SINGLETONS,
    BASE_MODEL,
    EMBEDDING_MODEL_NAME,
    OUTPUT_DIR,
    PIPELINE_VERSION,
    STAGE1_ADAPTER_REPO,
    STAGE3_ADAPTER_REPO,
    TASK1,
    TASK2,
    TASK3,
)
from .contracts import get_system_prompts
from .runtime import get_runtime
from .similarity import build_scope_embedding_cache, build_similarity_groups
from .storage import dump_json, load_json, write_csv
from .specification import build_gold_specification, specification_csv_rows
from .task1 import stage_task1
from .task2 import normalize_task2_global_ids, stage_task2, validate_document_task2_lineage
from .task3 import process_similarity_component, run_stage3_group, singleton_to_final, validate_final_task2_assignment
from .utils import canonical_json_sha256, dedupe_preserve, safe_file_component, text_sha256


def validate_user_input(input_obj: Any, source_name: str = "<memory>") -> dict:
    if not isinstance(input_obj, dict):
        raise TypeError(f"{source_name}: 최상위 JSON은 객체여야 합니다.")
    required_top = {"document_id", "document_name", "functional_requirements"}
    missing_top = required_top - set(input_obj)
    if missing_top:
        raise ValueError(f"{source_name}: 최상위 필드 누락 {sorted(missing_top)}")
    requirements = input_obj["functional_requirements"]
    if not isinstance(requirements, list) or not requirements:
        raise ValueError("functional_requirements는 1건 이상의 배열이어야 합니다.")
    required_fur = {"requirement_id", "requirement_name", "requirement_type", "requirement_definition", "requirement_detail"}
    seen_ids: set[str] = set()
    for index, fur in enumerate(requirements):
        if not isinstance(fur, dict):
            raise TypeError(f"functional_requirements[{index}]는 객체여야 합니다.")
        missing = required_fur - set(fur)
        if missing:
            raise ValueError(f"functional_requirements[{index}] 필드 누락={sorted(missing)}")
        fur_id = str(fur["requirement_id"]).strip()
        if not fur_id:
            raise ValueError(f"functional_requirements[{index}].requirement_id가 비어 있습니다.")
        if fur_id in seen_ids:
            raise ValueError(f"중복 requirement_id: {fur_id}")
        seen_ids.add(fur_id)
        if not str(fur["requirement_detail"]).strip():
            raise ValueError(f"{fur_id}.requirement_detail이 비어 있습니다.")
    scope_refs = input_obj.get("scope_reference_requirements", [])
    if not isinstance(scope_refs, list):
        raise TypeError("scope_reference_requirements는 배열이어야 합니다.")
    return input_obj


def enrich_final_lineage(final: dict, task2_by_id: dict[str, dict]) -> None:
    source_task2_ids = dedupe_preserve(final.get("source_task2_ids", []))
    source_atomic_ids = dedupe_preserve(final.get("source_atomic_ids", []))
    sources = dedupe_preserve(final.get("sources", []))
    for task2_id in source_task2_ids:
        source = task2_by_id.get(task2_id)
        if source:
            source_atomic_ids.extend(source.get("merged_from", []))
            sources.extend(source.get("source_requirement_ids", []))
    final["source_task2_ids"] = dedupe_preserve(source_task2_ids)
    final["source_atomic_ids"] = dedupe_preserve(source_atomic_ids)
    final["sources"] = dedupe_preserve(sources)


def _build_manifest(input_obj: dict, run_id: str) -> dict:
    runtime = get_runtime().start()
    prompts = get_system_prompts(runtime.hf_token or "")
    return {
        "pipeline_version": PIPELINE_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "document_id": str(input_obj["document_id"]).strip(),
        "input_sha256": canonical_json_sha256(input_obj),
        "contracts": {"base_model": BASE_MODEL, "stage1_adapter": STAGE1_ADAPTER_REPO, "stage3_adapter": STAGE3_ADAPTER_REPO, "embedding_model": EMBEDDING_MODEL_NAME},
        "prompt_hashes": {task: text_sha256(prompts[task]) for task in (TASK1, TASK2, TASK3)},
        "mode": "TASK1_FRESH_NO_EVALUATION",
    }


def _finalize_ids(finals: list[dict], relations: list[dict], task2_order: dict[str, int]) -> None:
    def sort_key(final: dict):
        positions = [task2_order[task2_id] for task2_id in final.get("source_task2_ids", []) if task2_id in task2_order]
        return (min(positions) if positions else 10**9, final.get("requirement_name", ""))

    finals.sort(key=sort_key)
    mapping: dict[str, str] = {}
    for index, final in enumerate(finals, start=1):
        old = str(final["gold_id"])
        new = f"GOLD-{index:03d}"
        mapping[old] = new
        final["gold_id"] = new
    for relation in relations:
        old = str(relation.get("gold_id", ""))
        if old not in mapping:
            raise ValueError(f"관계 판정 임시 GOLD ID 매핑 실패: {old}")
        relation["gold_id"] = mapping[old]


def run_document(input_obj: dict, *, output_dir: Path | str | None = None, run_id: str | None = None, replace_existing: bool = True) -> dict:
    """문서 객체를 TASK1부터 새로 처리하고 최종 GOLD 및 운영 trace를 반환한다."""
    input_obj = validate_user_input(input_obj)
    runtime = get_runtime().start()
    doc_id = str(input_obj["document_id"]).strip()
    doc_name = str(input_obj["document_name"]).strip()
    requirements = input_obj["functional_requirements"]
    scopes = input_obj.get("scope_reference_requirements", [])
    run_id = safe_file_component(run_id or doc_id)
    root = Path(output_dir or OUTPUT_DIR)
    doc_out = root / run_id
    if doc_out.exists():
        if not replace_existing:
            raise FileExistsError(f"이미 존재하는 실행 폴더: {doc_out}")
        shutil.rmtree(doc_out)
    raw_dir = doc_out / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    dump_json(doc_out / "input_document.json", input_obj)
    dump_json(doc_out / "run_manifest.json", _build_manifest(input_obj, run_id))

    all_atomics_by_fur: dict[str, list[dict]] = {}
    for index, fur in enumerate(requirements, start=1):
        fur_id = str(fur["requirement_id"]).strip()
        print(f"[TASK1] {index}/{len(requirements)} {fur_id}", flush=True)
        all_atomics_by_fur[fur_id] = stage_task1(doc_id, doc_name, fur, raw_log_path=raw_dir / "task1" / f"{safe_file_component(fur_id)}.json")
    dump_json(doc_out / "task1_atomics_by_fur.json", all_atomics_by_fur)

    local_candidates: list[dict] = []
    for index, fur in enumerate(requirements, start=1):
        fur_id = str(fur["requirement_id"]).strip()
        print(f"[TASK2] {index}/{len(requirements)} {fur_id}", flush=True)
        normalized = stage_task2(doc_id, fur_id, all_atomics_by_fur[fur_id], raw_log_path=raw_dir / "task2" / f"{safe_file_component(fur_id)}.json")
        local_candidates.extend(normalized)
    candidates = normalize_task2_global_ids(local_candidates)
    validate_document_task2_lineage(all_atomics_by_fur, candidates)
    dump_json(doc_out / "task2_candidates.json", {"task_type": TASK2, "document_id": doc_id, "candidate_requirement_count": len(candidates), "candidate_requirements": candidates})

    similarity_result = build_similarity_groups(doc_id, candidates, doc_out / "task3_embedding")
    components = similarity_result["similar_components"]
    singletons = similarity_result["singleton_indices"]
    scope_cache = build_scope_embedding_cache(scopes)
    global_scope = scope_cache.get("global_scope", [])
    task2_by_id = {item["task2_id"]: item for item in candidates}
    task2_order = {item["task2_id"]: index for index, item in enumerate(candidates)}
    combined_finals: list[dict] = []
    combined_relations: list[dict] = []
    fallback_records: list[dict] = []
    component_traces: list[dict] = []

    for singleton_no, candidate_index in enumerate(singletons, start=1):
        candidate = candidates[candidate_index]
        if APPLY_GLOBAL_SCOPE_TO_SINGLETONS and global_scope:
            group_id = f"{doc_id}-SCOPE-S{singleton_no:04d}"
            finals, relations, fallbacks = run_stage3_group(group_id, [{**candidate, "lineage_task2_ids": [candidate["task2_id"]]}], global_scope, raw_dir / "task3" / "singletons" / f"singleton_{singleton_no:04d}.json")
            fallback_records.extend(fallbacks)
            local_map: dict[str, str] = {}
            for local_index, final in enumerate(finals, start=1):
                final = dict(final)
                old = str(final.get("gold_id", "")).strip()
                temp = f"TMP-S{singleton_no:04d}-{local_index:02d}"
                if old:
                    local_map[old] = temp
                final["gold_id"] = temp
                enrich_final_lineage(final, task2_by_id)
                combined_finals.append(final)
            for relation in relations:
                relation = dict(relation)
                relation["gold_id"] = local_map.get(str(relation.get("gold_id", "")).strip(), relation.get("gold_id"))
                combined_relations.append(relation)
        else:
            final, relation = singleton_to_final(candidate, f"TMP-S-{singleton_no:04d}")
            combined_finals.append(final)
            combined_relations.append(relation)

    for component_no, indices in enumerate(components, start=1):
        group_candidates = [candidates[index] for index in indices]
        finals, relations, component_trace = process_similarity_component(doc_id, component_no, group_candidates, scope_cache, raw_dir / "task3" / f"component_{component_no:03d}")
        fallback_records.extend(component_trace.get("fallback_records", []))
        component_traces.append(component_trace)
        local_map: dict[str, str] = {}
        for local_index, final in enumerate(finals, start=1):
            final = dict(final)
            old = str(final.get("gold_id", "")).strip()
            temp = f"TMP-C{component_no:03d}-{local_index:04d}"
            if old:
                local_map[old] = temp
            final["gold_id"] = temp
            enrich_final_lineage(final, task2_by_id)
            combined_finals.append(final)
        for relation in relations:
            relation = dict(relation)
            relation["gold_id"] = local_map.get(str(relation.get("gold_id", "")).strip(), relation.get("gold_id"))
            combined_relations.append(relation)

    final_by_temp = {final["gold_id"]: final for final in combined_finals}
    for relation in combined_relations:
        target = final_by_temp.get(relation.get("gold_id"))
        if target is None:
            raise ValueError(f"존재하지 않는 임시 GOLD 참조: {relation.get('gold_id')}")
        relation_ids = dedupe_preserve(relation.get("comparison_ids", [])) + dedupe_preserve(relation.get("excluded_or_absorbed_ids", []))
        target["source_task2_ids"] = dedupe_preserve(target.get("source_task2_ids", []) + relation_ids)
        enrich_final_lineage(target, task2_by_id)

    _finalize_ids(combined_finals, combined_relations, task2_order)
    assignment = validate_final_task2_assignment(candidates, combined_finals, combined_relations)
    quality_status = "PASS" if not fallback_records else "REVIEW_REQUIRED"
    trace = {
        "pipeline_version": PIPELINE_VERSION,
        "document_id": doc_id,
        "run_id": run_id,
        "input_fur_count": len(requirements),
        "task1_atomic_total": sum(len(items) for items in all_atomics_by_fur.values()),
        "task2_candidate_total": len(candidates),
        "similar_component_count": len(components),
        "singleton_count": len(singletons),
        "task3_final_total": len(combined_finals),
        "task3_fallback_count": len(fallback_records),
        "quality_status": quality_status,
        "assignment_quality": assignment,
        "component_traces": component_traces,
    }
    gold_specification = build_gold_specification(combined_finals, input_obj)
    output = {
        "output_type": "GOLD_REQUIREMENT_SPECIFICATION",
        "task_type": TASK3,
        "document_id": doc_id,
        "document_name": doc_name,
        "input_type": "RFP_FUNCTIONAL_REQUIREMENTS",
        "final_requirement_count": len(combined_finals),
        "gold_requirement_count": len(gold_specification),
        "gold_requirement_specification": gold_specification,
        "final_requirements": combined_finals,
        "relation_decisions": combined_relations,
        "quality": {"status": quality_status, "fallback_count": len(fallback_records), "fallback_records": fallback_records, **assignment},
        "trace": trace,
    }
    dump_json(doc_out / "gold_requirement_specification.json", output)
    dump_json(doc_out / "GOLD.json", output)
    dump_json(root / f"{run_id}_gold_requirement_specification.json", output)
    write_csv(doc_out / "gold_requirement_specification.csv", specification_csv_rows(gold_specification))
    write_csv(doc_out / "GOLD.csv", [{"gold_id": item["gold_id"], "action_type": item.get("action_type", ""), "requirement_name": item.get("requirement_name", ""), "requirement_detail": item.get("requirement_detail", ""), "source_task2_ids": "; ".join(item.get("source_task2_ids", [])), "source_atomic_ids": "; ".join(item.get("source_atomic_ids", [])), "sources": "; ".join(item.get("sources", [])), "processing_type": item.get("processing_type", ""), "merge_basis": item.get("merge_basis", "")} for item in combined_finals])
    return output


def run_file(input_path: Path | str, *, output_dir: Path | str | None = None, run_id: str | None = None, replace_existing: bool = True) -> dict:
    input_path = Path(input_path)
    return run_document(validate_user_input(load_json(input_path), input_path.name), output_dir=output_dir, run_id=run_id, replace_existing=replace_existing)
