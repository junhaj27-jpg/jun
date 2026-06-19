from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .config import TASK2
from .runtime import get_runtime
from .storage import dump_json
from .task1 import validate_task1_result
from .utils import dedupe_preserve

def canonical_atomic_reference(source_fur_id: str, atomic_id: str) -> str:
    atomic_id = str(atomic_id).strip()
    if not atomic_id:
        return ''
    if '::' in atomic_id:
        return atomic_id
    return f'{source_fur_id}::{atomic_id}'

def normalize_task2_local_output(source_fur_id: str, normalized: list[dict]) -> list[dict]:
    result = []
    for item in normalized:
        item = dict(item)
        item['source_fur_id'] = source_fur_id
        item['source_requirement_ids'] = dedupe_preserve(item.get('source_requirement_ids', []) + [source_fur_id])
        item['merged_from'] = dedupe_preserve((canonical_atomic_reference(source_fur_id, value) for value in item.get('merged_from', [])))
        item['reference_context_ids'] = dedupe_preserve((canonical_atomic_reference(source_fur_id, value) for value in item.get('reference_context_ids', [])))
        result.append(item)
    return result

def _lineage_tokens(value: Any) -> set[str]:
    return {token for token in re.findall(r'[0-9A-Za-z가-힣]+', str(value).lower()) if len(token) >= 2}

def _task2_owner_score(atomic: dict, item: dict, atomic_id: str) -> tuple[float, int]:
    merged_from = dedupe_preserve(item.get('merged_from', []))
    atomic_action = str(atomic.get('action_type', '')).strip()
    item_action = str(item.get('action_type', '')).strip()
    atomic_text = ' '.join((str(atomic.get('output_name', '')), str(atomic.get('source_text', '')), str(atomic.get('requirement_detail', ''))))
    item_text = ' '.join((str(item.get('requirement_name', '')), str(item.get('requirement_detail', ''))))
    left, right = _lineage_tokens(atomic_text), _lineage_tokens(item_text)
    overlap = len(left & right) / max(1, len(left | right))
    score = overlap * 10.0 + (3.0 if atomic_action and atomic_action == item_action else 0.0)
    if merged_from == [atomic_id]:
        score += 100.0
    return score, -len(merged_from)

def repair_task2_primary_assignments(atomics: list[dict], normalized: list[dict]) -> tuple[list[dict], list[dict]]:
    atomic_by_id = {str(item['atomic_id']).strip(): item for item in atomics}
    repaired = [dict(item) for item in normalized]
    assignments = defaultdict(list)
    for index, item in enumerate(repaired):
        item['merged_from'] = dedupe_preserve(item.get('merged_from', []))
        item['reference_context_ids'] = dedupe_preserve(item.get('reference_context_ids', []))
        for atomic_id in item['merged_from']:
            assignments[atomic_id].append(index)
    records = []
    for atomic_id, indices in assignments.items():
        if len(indices) <= 1:
            continue
        atomic = atomic_by_id.get(atomic_id, {})
        owner_index = max(indices, key=lambda index: (_task2_owner_score(atomic, repaired[index], atomic_id), -index))
        owner_task2_id = str(repaired[owner_index].get('task2_id', '')).strip()
        moved_to_reference = []
        for index in indices:
            if index == owner_index:
                continue
            item = repaired[index]
            item['merged_from'] = [value for value in item['merged_from'] if value != atomic_id]
            item['reference_context_ids'] = dedupe_preserve(item['reference_context_ids'] + [atomic_id])
            moved_to_reference.append(str(item.get('task2_id', '')).strip())
        records.append({'atomic_id': atomic_id, 'kept_in_merged_from': owner_task2_id, 'moved_to_reference_context_ids': moved_to_reference})
    dropped = []
    kept = []
    for item in repaired:
        if item.get('merged_from'):
            kept.append(item)
        else:
            dropped.append({'task2_id': str(item.get('task2_id', '')).strip(), 'reason': '중복 주 계보 정리 후 merged_from이 비어 과분해 결과로 판단', 'reference_context_ids': item.get('reference_context_ids', [])})
    records.extend({'dropped_unanchored_task2': item} for item in dropped)
    return kept, records

def repair_task2_missing_atomic_assignments(source_fur_id: str, atomics: list[dict], normalized: list[dict]) -> tuple[list[dict], list[dict]]:
    expected_ids = {str(item['atomic_id']).strip() for item in atomics}
    referenced_ids = set()
    primary_ids = set()
    existing_task2_ids = {str(item.get('task2_id', '')).strip() for item in normalized}

    for item in normalized:
        merged_from = dedupe_preserve(item.get('merged_from', []))
        reference_ids = dedupe_preserve(item.get('reference_context_ids', []))
        referenced_ids.update(merged_from)
        referenced_ids.update(reference_ids)
        primary_ids.update(merged_from)

    missing_ids = sorted(expected_ids - primary_ids)
    if not missing_ids:
        return normalized, []

    atomic_by_id = {str(item['atomic_id']).strip(): item for item in atomics}
    repaired = [dict(item) for item in normalized]
    records = []

    for repair_index, atomic_id in enumerate(missing_ids, start=1):
        atomic = atomic_by_id[atomic_id]
        task2_id = f'AUTO-T2-{repair_index:03d}'
        while task2_id in existing_task2_ids:
            repair_index += 1
            task2_id = f'AUTO-T2-{repair_index:03d}'
        existing_task2_ids.add(task2_id)

        requirement_name = str(atomic.get('output_name', '')).strip() or str(atomic.get('source_text', '')).strip()[:100] or atomic_id
        requirement_detail = str(atomic.get('source_text', '')).strip() or str(atomic.get('requirement_detail', '')).strip() or requirement_name

        fallback = {
            'task2_id': task2_id,
            'merge_decision': 'KEPT',
            'merged_from': [atomic_id],
            'reference_context_ids': [],
            'action_type': str(atomic.get('action_type', '')).strip() or '미지정',
            'requirement_name': requirement_name,
            'requirement_detail': requirement_detail,
            'source_requirement_ids': [source_fur_id],
            'source_fur_id': source_fur_id,
        }
        repaired.append(fallback)
        records.append({
            'atomic_id': atomic_id,
            'created_task2_id': task2_id,
            'reason': 'TASK2 output omitted this atomic from merged_from; preserved as an independent candidate.',
        })

    return repaired, records

def validate_task2_atomic_coverage(atomics: list[dict], normalized: list[dict]) -> None:
    expected_ids = {str(item['atomic_id']).strip() for item in atomics}
    referenced_ids = set()
    primary_assignment = defaultdict(list)
    for item in normalized:
        task2_id = str(item.get('task2_id', '')).strip()
        merged_from = dedupe_preserve(item.get('merged_from', []))
        reference_ids = dedupe_preserve(item.get('reference_context_ids', []))
        referenced_ids.update(merged_from)
        referenced_ids.update(reference_ids)
        for atomic_id in merged_from:
            primary_assignment[atomic_id].append(task2_id)
    unknown = sorted(referenced_ids - expected_ids)
    missing_reference = sorted(expected_ids - referenced_ids)
    missing_primary = sorted(expected_ids - set(primary_assignment))
    duplicate_primary = {atomic_id: task2_ids for atomic_id, task2_ids in primary_assignment.items() if len(set(task2_ids)) > 1}
    if unknown:
        raise ValueError(f'TASK2가 생성한 알 수 없는 atomic ID: {unknown}')
    if missing_reference:
        raise ValueError(f'TASK2에서 완전히 누락된 atomic ID: {missing_reference}')
    if missing_primary:
        raise ValueError(f'TASK2 merged_from 주 계보가 없는 atomic ID: {missing_primary}')
    if duplicate_primary:
        raise ValueError(f'TASK2 merged_from에 중복 배정된 atomic ID: {duplicate_primary}')

def stage_task2(doc_id: str, source_requirement_id: str, atomics: list[dict], *, raw_log_path: Path) -> list[dict]:
    if not isinstance(atomics, list) or not atomics:
        raise TypeError('TASK2 atomic_requirements는 1건 이상의 배열이어야 합니다.')
    validate_task1_result(source_requirement_id, atomics)
    atomic_ids = [str(item['atomic_id']).strip() for item in atomics]
    user_obj = {'task_type': TASK2, 'document_id': doc_id, 'source_requirement_id': source_requirement_id, 'atomic_requirements': atomics, 'reference_contexts': [], 'lineage_constraints': {'all_atomic_ids': atomic_ids, 'merged_from_rule': '각 atomic_id는 normalized_requirements 전체의 merged_from에 정확히 1회만 배정한다.', 'reference_context_rule': '다른 요구사항의 참고 근거로 재사용할 때만 reference_context_ids에 넣는다.', 'no_new_ids': True}}
    obj, _ = get_runtime().run_task(TASK2, user_obj, raw_log_path=raw_log_path)
    normalized = normalize_task2_local_output(source_requirement_id, obj['normalized_requirements'])
    normalized, repair_records = repair_task2_primary_assignments(atomics, normalized)
    normalized, missing_repair_records = repair_task2_missing_atomic_assignments(source_requirement_id, atomics, normalized)
    repair_records.extend({'missing_atomic_fallback': item} for item in missing_repair_records)
    if repair_records:
        repair_path = raw_log_path.with_name(f'{raw_log_path.stem}_lineage_repair.json')
        dump_json(repair_path, {'task_type': TASK2, 'document_id': doc_id, 'source_requirement_id': source_requirement_id, 'repair_count': len(repair_records), 'repairs': repair_records, 'normalized_requirements_after_repair': normalized})
        print(f'[TASK2 계보 자동 복구] fur={source_requirement_id}, repairs={len(repair_records)}, log={repair_path}', flush=True)
    validate_task2_atomic_coverage(atomics, normalized)
    return normalized

def normalize_task2_global_ids(candidates: list[dict]) -> list[dict]:
    normalized = []
    original_counts = defaultdict(int)
    for index, raw_item in enumerate(candidates, start=1):
        item = dict(raw_item)
        original_task2_id = str(item.get('task2_id', '')).strip() or f'LOCAL-T2-{index:06d}'
        original_counts[original_task2_id] += 1
        item['original_task2_id'] = original_task2_id
        item['task2_id'] = f'T2-{index:06d}'
        item['source_requirement_ids'] = dedupe_preserve(item.get('source_requirement_ids', []))
        source_fur_id = str(item.get('source_fur_id', '')).strip()
        if not source_fur_id and item['source_requirement_ids']:
            source_fur_id = item['source_requirement_ids'][0]
        if source_fur_id:
            item['source_requirement_ids'] = dedupe_preserve(item['source_requirement_ids'] + [source_fur_id])
        item['source_fur_id'] = source_fur_id
        item['merged_from'] = dedupe_preserve((canonical_atomic_reference(source_fur_id, value) if source_fur_id else str(value).strip() for value in item.get('merged_from', [])))
        item['reference_context_ids'] = dedupe_preserve((canonical_atomic_reference(source_fur_id, value) if source_fur_id else str(value).strip() for value in item.get('reference_context_ids', [])))
        item['action_type'] = str(item.get('action_type', '미지정')).strip() or '미지정'
        item['requirement_name'] = str(item.get('requirement_name', '')).strip()
        item['requirement_detail'] = str(item.get('requirement_detail', '')).strip()
        if not item['requirement_name']:
            raise ValueError(f"{item['task2_id']}.requirement_name이 비어 있습니다.")
        if not item['requirement_detail']:
            raise ValueError(f"{item['task2_id']}.requirement_detail이 비어 있습니다.")
        normalized.append(item)
    duplicate_original_ids = {key: value for key, value in original_counts.items() if value > 1}
    print(f"[TASK2 전역 ID 정규화] count={len(normalized)}, duplicated_local_id_types={len(duplicate_original_ids)}, range={normalized[0]['task2_id']}~{normalized[-1]['task2_id']}", flush=True)
    return normalized

def validate_document_task2_lineage(all_atomics_by_fur: dict[str, list[dict]], candidates: list[dict]) -> None:
    all_atomics = [item for atomics in all_atomics_by_fur.values() for item in atomics]
    validate_task2_atomic_coverage(all_atomics, candidates)

def extract_saved_task2_candidates(saved_obj: Any) -> list[dict]:
    if isinstance(saved_obj, list):
        candidates = saved_obj
    elif isinstance(saved_obj, dict):
        candidates = None
        for key in ('candidate_requirements', 'normalized_requirements', 'task2_candidates', 'requirements'):
            value = saved_obj.get(key)
            if isinstance(value, list):
                candidates = value
                print(f'[TASK2 저장 배열 선택] key={key}, count={len(value)}')
                break
        if candidates is None:
            raise ValueError('저장된 TASK2 후보 배열을 찾지 못했습니다.')
    else:
        raise TypeError('저장된 TASK2 파일의 최상위 형식이 올바르지 않습니다.')
    if not candidates:
        raise ValueError('저장된 TASK2 후보가 0건입니다.')
    return normalize_task2_global_ids(candidates)
