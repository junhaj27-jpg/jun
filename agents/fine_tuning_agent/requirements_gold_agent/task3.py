from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np

from .config import EMBEDDING_BATCH_SIZE, TASK3, TASK3_COVERAGE_FALLBACK_ENABLED, TASK3_MAX_GROUP_SIZE, TASK3_MAX_LOCAL_ROUNDS
from .runtime import get_runtime
from .similarity import embedding_text, get_embedding_model, select_scope_for_group, split_indices_by_similarity
from .storage import dump_json
from .utils import dedupe_preserve

def task3_payload_candidate(item: dict) -> dict:
    return {'task2_id': item['task2_id'], 'merge_decision': item.get('merge_decision', 'KEPT'), 'merged_from': dedupe_preserve(item.get('merged_from', [])), 'reference_context_ids': dedupe_preserve(item.get('reference_context_ids', [])), 'action_type': item.get('action_type', '미지정'), 'requirement_name': item.get('requirement_name', ''), 'requirement_detail': item.get('requirement_detail', ''), 'source_requirement_ids': dedupe_preserve(item.get('source_requirement_ids', []))}

def make_task3_user_obj(doc_id: str, candidates: list[dict], scope_reference_requirements: list[dict]) -> dict:
    return {'task_type': TASK3, 'document_id': doc_id, 'candidate_requirements': [task3_payload_candidate(item) for item in candidates], 'scope_reference_requirements': scope_reference_requirements}

def map_ids_to_original_lineage(ids, input_lineage_map: dict[str, list[str]]) -> list[str]:
    result = []
    for item_id in dedupe_preserve(ids):
        result.extend(input_lineage_map.get(item_id, [item_id]))
    return dedupe_preserve(result)

def resolve_stage3_lineage(finals: list[dict], relations: list[dict], input_candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    input_lineage_map = {item['task2_id']: dedupe_preserve(item.get('lineage_task2_ids', [item['task2_id']])) for item in input_candidates}
    finals_by_gold = {}
    for final in finals:
        final['source_task2_ids'] = map_ids_to_original_lineage(final.get('source_task2_ids', []), input_lineage_map)
        finals_by_gold[str(final.get('gold_id', '')).strip()] = final
    normalized_relations = []
    for raw_relation in relations:
        if not isinstance(raw_relation, dict):
            continue
        relation = dict(raw_relation)
        relation['comparison_ids'] = map_ids_to_original_lineage(relation.get('comparison_ids', []), input_lineage_map)
        relation['excluded_or_absorbed_ids'] = map_ids_to_original_lineage(relation.get('excluded_or_absorbed_ids', []), input_lineage_map)
        target = finals_by_gold.get(str(relation.get('gold_id', '')).strip())
        if target is not None:
            target['source_task2_ids'] = dedupe_preserve(target.get('source_task2_ids', []) + relation['comparison_ids'] + relation['excluded_or_absorbed_ids'])
        normalized_relations.append(relation)
    return (finals, normalized_relations)

def expected_group_lineage_ids(input_candidates: list[dict]) -> set[str]:
    return {original_id for candidate in input_candidates for original_id in dedupe_preserve(candidate.get('lineage_task2_ids', [candidate['task2_id']]))}

def covered_group_lineage_ids(finals: list[dict]) -> set[str]:
    covered_ids = set()
    for final in finals:
        covered_ids.update(dedupe_preserve(final.get('source_task2_ids', [])))
    return covered_ids

def find_missing_group_coverage(input_candidates: list[dict], finals: list[dict], relations: list[dict] | None=None) -> list[str]:
    expected_ids = expected_group_lineage_ids(input_candidates)
    covered_ids = covered_group_lineage_ids(finals)
    return sorted(expected_ids - covered_ids)

def repair_duplicate_final_task2_assignment(group_doc_id: str, finals: list[dict], relations: list[dict], raw_log_path: Path) -> tuple[list[dict], list[dict], list[dict]]:
    assignment = defaultdict(list)
    for final_index, final in enumerate(finals):
        gold_id = str(final.get('gold_id', '')).strip()
        task2_ids = dedupe_preserve(final.get('source_task2_ids', []))
        for task2_id in task2_ids:
            assignment[task2_id].append({'final_index': final_index, 'gold_id': gold_id, 'source_count': len(task2_ids)})

    duplicate_owners = {
        task2_id: owners
        for task2_id, owners in assignment.items()
        if len({owner['gold_id'] for owner in owners}) > 1
    }
    if not duplicate_owners:
        return (finals, relations, [])

    keep_owner_by_task2 = {}
    for task2_id, owners in duplicate_owners.items():
        valid_owners = [owner for owner in owners if owner['gold_id']]
        selected = sorted(valid_owners or owners, key=lambda owner: (owner['source_count'], owner['final_index']))[0]
        keep_owner_by_task2[task2_id] = selected['gold_id']

    repaired_finals = []
    dropped_gold_ids = set()
    repair_records = []

    for final in finals:
        gold_id = str(final.get('gold_id', '')).strip()
        original_task2_ids = dedupe_preserve(final.get('source_task2_ids', []))
        kept_task2_ids = [
            task2_id
            for task2_id in original_task2_ids
            if task2_id not in keep_owner_by_task2 or keep_owner_by_task2[task2_id] == gold_id
        ]
        removed_task2_ids = [
            task2_id
            for task2_id in original_task2_ids
            if task2_id in keep_owner_by_task2 and keep_owner_by_task2[task2_id] != gold_id
        ]
        if removed_task2_ids:
            repair_records.append({
                'gold_id': gold_id,
                'removed_task2_ids': removed_task2_ids,
                'kept_owner_by_task2': {task2_id: keep_owner_by_task2[task2_id] for task2_id in removed_task2_ids},
                'reason': 'TASK3 output assigned the same TASK2 IDs to multiple final requirements.',
            })
        if kept_task2_ids:
            repaired_final = dict(final)
            repaired_final['source_task2_ids'] = kept_task2_ids
            repaired_finals.append(repaired_final)
        else:
            dropped_gold_ids.add(gold_id)
            repair_records.append({
                'gold_id': gold_id,
                'dropped': True,
                'reason': 'All source_task2_ids were already assigned to more specific final requirements.',
            })

    repaired_gold_ids = {str(final.get('gold_id', '')).strip() for final in repaired_finals}
    repaired_relations = []
    for relation in relations:
        if not isinstance(relation, dict):
            continue
        relation_gold_id = str(relation.get('gold_id', '')).strip()
        if relation_gold_id in dropped_gold_ids or relation_gold_id not in repaired_gold_ids:
            continue
        repaired_relation = dict(relation)
        for key in ('comparison_ids', 'excluded_or_absorbed_ids'):
            repaired_relation[key] = [
                task2_id
                for task2_id in dedupe_preserve(repaired_relation.get(key, []))
                if task2_id not in keep_owner_by_task2 or keep_owner_by_task2[task2_id] == relation_gold_id
            ]
        repaired_relations.append(repaired_relation)

    repair_path = raw_log_path.with_name(f'{raw_log_path.stem}_duplicate_assignment_repair.json')
    dump_json(repair_path, {
        'group_document_id': group_doc_id,
        'duplicate_owners': duplicate_owners,
        'keep_owner_by_task2': keep_owner_by_task2,
        'repair_records': repair_records,
        'final_count_before': len(finals),
        'final_count_after': len(repaired_finals),
    })
    print(f'[TASK3 중복 배정 보정] group={group_doc_id}, duplicates={len(duplicate_owners)}, final_count={len(finals)}->{len(repaired_finals)}', flush=True)

    return (repaired_finals, repaired_relations, repair_records)

def validate_final_task2_assignment(candidates: list[dict], finals: list[dict], relations: list[dict]) -> dict:
    expected_ids = {item['task2_id'] for item in candidates}
    final_gold_ids = {str(item.get('gold_id', '')).strip() for item in finals}
    if '' in final_gold_ids:
        raise ValueError('빈 gold_id가 있습니다.')
    orphan_relations = [relation for relation in relations if str(relation.get('gold_id', '')).strip() not in final_gold_ids]
    if orphan_relations:
        raise ValueError(f'존재하지 않는 GOLD를 참조하는 관계 판정이 있습니다: {orphan_relations[:3]}')
    assignment = defaultdict(list)
    unknown_final_ids = set()
    for final in finals:
        gold_id = str(final['gold_id']).strip()
        for task2_id in dedupe_preserve(final.get('source_task2_ids', [])):
            if task2_id not in expected_ids:
                unknown_final_ids.add(task2_id)
            assignment[task2_id].append(gold_id)
    unknown_relation_ids = set()
    for relation in relations:
        for task2_id in dedupe_preserve(relation.get('comparison_ids', [])) + dedupe_preserve(relation.get('excluded_or_absorbed_ids', [])):
            if task2_id not in expected_ids:
                unknown_relation_ids.add(task2_id)
    if unknown_final_ids:
        raise ValueError(f'최종 GOLD의 알 수 없는 TASK2 ID: {sorted(unknown_final_ids)}')
    if unknown_relation_ids:
        raise ValueError(f'관계 판정의 알 수 없는 TASK2 ID: {sorted(unknown_relation_ids)}')
    missing = sorted((task2_id for task2_id in expected_ids if not assignment[task2_id]))
    duplicated = {task2_id: gold_ids for task2_id, gold_ids in assignment.items() if len(set(gold_ids)) > 1}
    if missing:
        raise ValueError(f'최종 GOLD에 포함되지 않은 TASK2 ID: {missing}')
    if duplicated:
        raise ValueError(f'여러 GOLD에 중복 배정된 TASK2 ID: {duplicated}')
    return {'expected_task2_count': len(expected_ids), 'assigned_task2_count': len(assignment), 'missing_task2_count': 0, 'duplicate_assignment_count': 0, 'orphan_relation_count': 0}

def restore_missing_group_coverage(group_doc_id: str, input_candidates: list[dict], finals: list[dict], relations: list[dict], raw_log_path: Path) -> tuple[list[dict], list[dict], list[dict]]:
    """
    모델 출력에서 완전히 사라진 입력 후보만 독립 유지로 복구합니다.

    중복/병합 여부를 임의로 판단하지 않으며, 누락으로 인한 데이터
    손실을 막는 보수적 fallback입니다.
    """
    missing_ids = find_missing_group_coverage(input_candidates, finals, relations)
    if not missing_ids:
        return (finals, relations, [])
    if not TASK3_COVERAGE_FALLBACK_ENABLED:
        raise ValueError(f'TASK3 그룹 계보 누락: {missing_ids}')
    missing_set = set(missing_ids)
    existing_gold_ids = {str(item.get('gold_id', '')).strip() for item in finals if isinstance(item, dict)}
    fallback_records = []
    fallback_no = 1
    for candidate in input_candidates:
        candidate_lineage = dedupe_preserve(candidate.get('lineage_task2_ids', [candidate['task2_id']]))
        missing_for_candidate = [lineage_id for lineage_id in candidate_lineage if lineage_id in missing_set]
        if not missing_for_candidate:
            continue
        while True:
            fallback_gold_id = f'GOLD-COVERAGE-{fallback_no:03d}'
            fallback_no += 1
            if fallback_gold_id not in existing_gold_ids:
                break
        existing_gold_ids.add(fallback_gold_id)
        fallback_final = {'gold_id': fallback_gold_id, 'action_type': candidate.get('action_type', '미지정'), 'requirement_name': candidate.get('requirement_name', ''), 'requirement_detail': candidate.get('requirement_detail', ''), 'source_task2_ids': candidate_lineage, 'source_atomic_ids': dedupe_preserve(candidate.get('merged_from', [])), 'sources': dedupe_preserve(candidate.get('source_requirement_ids', [])), 'processing_type': 'KEPT', 'merge_basis': 'TASK3 유사 그룹 출력에서 해당 입력 계보가 최종 요구사항과 관계 판정 모두에서 누락되어 데이터 손실 방지를 위해 입력 요구사항을 독립 요구사항으로 보존함'}
        fallback_relation = {'relation_type': 'UNIQUE', 'processing_result': 'KEPT', 'comparison_ids': candidate_lineage, 'excluded_or_absorbed_ids': [], 'gold_id': fallback_gold_id, 'preserved_conditions': ['TASK3 그룹 출력 계보 누락으로 원문 전체 보존'], 'rationale': 'COVERAGE_FALLBACK_KEPT: 모델 출력에서 입력 후보가 누락되어 임의 병합 없이 독립 유지함'}
        finals.append(fallback_final)
        relations.append(fallback_relation)
        fallback_records.append({'group_document_id': group_doc_id, 'fallback_gold_id': fallback_gold_id, 'current_candidate_id': candidate.get('task2_id'), 'candidate_lineage': candidate_lineage, 'missing_lineage_ids': missing_for_candidate, 'action': 'COVERAGE_FALLBACK_KEPT', 'requirement_name': candidate.get('requirement_name', '')})
    still_missing = find_missing_group_coverage(input_candidates, finals, relations)
    if still_missing:
        raise ValueError(f'TASK3 계보 fallback 후에도 누락: {still_missing}')
    repair_path = raw_log_path.with_name(f'{raw_log_path.stem}_coverage_repair.json')
    dump_json(repair_path, {'group_document_id': group_doc_id, 'missing_before_repair': missing_ids, 'fallback_count': len(fallback_records), 'fallback_records': fallback_records})
    print(f'[TASK3 계보 안전 복구] group={group_doc_id}, missing={missing_ids}, fallback_kept={len(fallback_records)}', flush=True)
    return (finals, relations, fallback_records)

def validate_group_coverage(input_candidates: list[dict], finals: list[dict], relations: list[dict]) -> None:
    missing = find_missing_group_coverage(input_candidates, finals, relations)
    if missing:
        raise ValueError(f'TASK3 그룹 계보 누락: {missing}')

def run_stage3_group(group_doc_id: str, group_candidates: list[dict], selected_scope: list[dict], raw_log_path: Path) -> tuple[list[dict], list[dict], list[dict]]:
    if not group_candidates:
        raise ValueError('TASK3 유사 그룹 후보가 비어 있습니다.')
    if len(group_candidates) > TASK3_MAX_GROUP_SIZE:
        raise ValueError(f'TASK3 유사 그룹 크기 초과: {len(group_candidates)} > {TASK3_MAX_GROUP_SIZE}')

    user_obj = make_task3_user_obj(group_doc_id, group_candidates, selected_scope)

    try:
        obj, _ = get_runtime().run_task(TASK3, user_obj, raw_log_path=raw_log_path)
        finals = [dict(item) for item in obj['final_requirements']]
        relations = [dict(item) for item in obj.get('relation_decisions', []) if isinstance(item, dict)]
        local_gold_ids = [str(item.get('gold_id', '')).strip() for item in finals]
        if not all(local_gold_ids) or len(local_gold_ids) != len(set(local_gold_ids)):
            raise ValueError('TASK3 그룹 출력의 gold_id가 비어 있거나 중복되었습니다.')
    except ValueError as e:
        if 'final_requirements가 0건입니다' not in str(e):
            raise
        print(f'[TASK3 빈 출력 감지] group={group_doc_id}, candidates={len(group_candidates)} -> coverage fallback 수행', flush=True)
        finals = []
        relations = []

    finals, relations = resolve_stage3_lineage(finals, relations, group_candidates)
    finals, relations, coverage_fallback_records = restore_missing_group_coverage(group_doc_id, group_candidates, finals, relations, raw_log_path)
    finals, relations, duplicate_repair_records = repair_duplicate_final_task2_assignment(group_doc_id, finals, relations, raw_log_path)
    coverage_fallback_records.extend({'duplicate_assignment_repair': item} for item in duplicate_repair_records)
    validate_group_coverage(group_candidates, finals, relations)
    validate_final_task2_assignment([{**candidate, 'task2_id': lineage_id} for candidate in group_candidates for lineage_id in dedupe_preserve(candidate.get('lineage_task2_ids', [candidate['task2_id']]))], finals, relations)

    return (finals, relations, coverage_fallback_records)

def final_to_local_candidate(final: dict, local_id: str) -> dict:
    return {'task2_id': local_id, 'merge_decision': 'KEPT', 'merged_from': dedupe_preserve(final.get('source_atomic_ids', [])), 'reference_context_ids': [], 'action_type': final.get('action_type', '미지정'), 'requirement_name': final.get('requirement_name', ''), 'requirement_detail': final.get('requirement_detail', ''), 'source_requirement_ids': dedupe_preserve(final.get('sources', [])), 'lineage_task2_ids': dedupe_preserve(final.get('source_task2_ids', []))}

def embed_candidate_list(candidates: list[dict]) -> np.ndarray:
    return get_embedding_model().encode([embedding_text(item) for item in candidates], batch_size=EMBEDDING_BATCH_SIZE, show_progress_bar=False, normalize_embeddings=True, convert_to_numpy=True)

def process_similarity_component(doc_id: str, component_no: int, component_candidates: list[dict], scope_cache: dict, raw_component_dir: Path) -> tuple[list[dict], list[dict], dict]:
    current_candidates = [{**dict(item), 'lineage_task2_ids': dedupe_preserve(item.get('lineage_task2_ids', [item['task2_id']]))} for item in component_candidates]
    trace_rounds = []
    for round_no in range(1, TASK3_MAX_LOCAL_ROUNDS + 1):
        current_embeddings = embed_candidate_list(current_candidates)
        current_similarity = current_embeddings @ current_embeddings.T
        current_indices = list(range(len(current_candidates)))
        chunks = split_indices_by_similarity(current_indices, current_similarity, TASK3_MAX_GROUP_SIZE)
        round_finals = []
        round_relations = []
        round_fallback_records = []
        print(f'[TASK3 컴포넌트] component={component_no}, round={round_no}, candidates={len(current_candidates)}, chunks={len(chunks)}', flush=True)
        for chunk_no, chunk_indices in enumerate(chunks, start=1):
            chunk_candidates = [current_candidates[index] for index in chunk_indices]
            chunk_embeddings = current_embeddings[chunk_indices]
            selected_scope = select_scope_for_group(chunk_candidates, chunk_embeddings, scope_cache)
            group_doc_id = f'{doc_id}-EMB-C{component_no:03d}-R{round_no:02d}-G{chunk_no:03d}'
            finals, relations, fallback_records = run_stage3_group(group_doc_id, chunk_candidates, selected_scope, raw_component_dir / f'round_{round_no:02d}' / f'group_{chunk_no:03d}.json')
            round_finals.extend(finals)
            round_relations.extend(relations)
            round_fallback_records.extend(fallback_records)
        trace_rounds.append({'round': round_no, 'input_candidate_count': len(current_candidates), 'chunk_count': len(chunks), 'output_final_count': len(round_finals), 'fallback_count': len(round_fallback_records)})
        if len(chunks) == 1:
            return (round_finals, round_relations, {'component_no': component_no, 'initial_count': len(component_candidates), 'rounds': trace_rounds, 'status': 'COMPLETED', 'fallback_records': round_fallback_records})
        next_candidates = [final_to_local_candidate(final, f'H3-C{component_no:03d}-R{round_no:02d}-{index:04d}') for index, final in enumerate(round_finals, start=1)]
        if not next_candidates:
            raise RuntimeError('TASK3 로컬 다음 라운드 후보가 0건입니다.')
        current_candidates = next_candidates
    print(f'[경고] TASK3 컴포넌트 {component_no}: 최대 로컬 라운드 {TASK3_MAX_LOCAL_ROUNDS}회에 도달했습니다. 마지막 소규모 그룹 결과를 결합합니다.', flush=True)
    return (round_finals, round_relations, {'component_no': component_no, 'initial_count': len(component_candidates), 'rounds': trace_rounds, 'status': 'MAX_LOCAL_ROUNDS_REACHED', 'fallback_records': round_fallback_records})

def singleton_to_final(candidate: dict, temp_gold_id: str) -> tuple[dict, dict]:
    final = {'gold_id': temp_gold_id, 'action_type': candidate.get('action_type', '미지정'), 'requirement_name': candidate.get('requirement_name', ''), 'requirement_detail': candidate.get('requirement_detail', ''), 'source_task2_ids': [candidate['task2_id']], 'source_atomic_ids': dedupe_preserve(candidate.get('merged_from', [])), 'sources': dedupe_preserve(candidate.get('source_requirement_ids', [])), 'processing_type': 'KEPT', 'merge_basis': '문서 전체 TASK2 후보 임베딩 비교에서 설정 임계값 이상의 유사 후보가 없어 TASK2 내용을 그대로 보존함'}
    relation = {'relation_type': 'UNIQUE', 'processing_result': 'KEPT', 'comparison_ids': [candidate['task2_id']], 'excluded_or_absorbed_ids': [], 'gold_id': temp_gold_id, 'preserved_conditions': [], 'rationale': '임베딩 유사 후보 없음'}
    return (final, relation)
