from __future__ import annotations

import json
import re
from .config import OUTPUT_SCHEMAS, TASK1, TASK2, TASK3
from .utils import dedupe_preserve

RELATION_REQUIRED_KEYS = {"relation_type", "processing_result", "comparison_ids", "excluded_or_absorbed_ids", "gold_id", "preserved_conditions", "rationale"}
ALLOWED_RELATION_TYPES = {"EXACT_DUPLICATE", "SEMANTIC_DUPLICATE", "PARTIAL_OVERLAP", "PARENT_CHILD", "RELATED_DISTINCT", "UNIQUE"}
ALLOWED_PROCESSING_RESULTS = {"MERGED", "ABSORBED", "KEPT", "SEPARATED"}

def _first_nonempty(mapping: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = mapping.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ''

def _normalize_relation_type(value: str) -> str:
    token = re.sub(r'[^A-Z0-9]+', '_', str(value or '').upper()).strip('_')
    aliases = {
        'EXACT': 'EXACT_DUPLICATE', 'EXACT_DUP': 'EXACT_DUPLICATE', 'EXACT_DUPLICATE': 'EXACT_DUPLICATE',
        'DUPLICATE': 'SEMANTIC_DUPLICATE', 'SEMANTIC': 'SEMANTIC_DUPLICATE', 'SEMANTIC_DUP': 'SEMANTIC_DUPLICATE', 'SEMANTIC_DUPLICATE': 'SEMANTIC_DUPLICATE',
        'PARTIAL': 'PARTIAL_OVERLAP', 'OVERLAP': 'PARTIAL_OVERLAP', 'PARTIAL_OVERLAP': 'PARTIAL_OVERLAP',
        'PARENT_CHILD': 'PARENT_CHILD', 'PARENTCHILD': 'PARENT_CHILD', 'HIERARCHY': 'PARENT_CHILD', 'ABSORBED': 'PARENT_CHILD',
        'RELATED': 'RELATED_DISTINCT', 'DISTINCT': 'RELATED_DISTINCT', 'RELATED_DISTINCT': 'RELATED_DISTINCT', 'SEPARATED': 'RELATED_DISTINCT',
        'UNIQUE': 'UNIQUE', 'KEEP': 'UNIQUE', 'KEPT': 'UNIQUE',
    }
    return aliases.get(token, token)

def _normalize_processing_result(value: str) -> str:
    token = re.sub(r'[^A-Z0-9]+', '_', str(value or '').upper()).strip('_')
    aliases = {
        'MERGE': 'MERGED', 'MERGED': 'MERGED', 'COMBINED': 'MERGED',
        'ABSORB': 'ABSORBED', 'ABSORBED': 'ABSORBED',
        'KEEP': 'KEPT', 'KEPT': 'KEPT', 'PRESERVED': 'KEPT', 'UNIQUE': 'KEPT',
        'SEPARATE': 'SEPARATED', 'SEPARATED': 'SEPARATED', 'DISTINCT': 'SEPARATED',
    }
    return aliases.get(token, token)

def _infer_relation_gold_id(relation: dict, finals: list[dict]) -> str:
    direct = _first_nonempty(relation, ('gold_id', 'final_gold_id', 'target_gold_id', 'result_gold_id'))
    valid_ids = {str(item.get('gold_id', '')).strip() for item in finals if isinstance(item, dict)}
    if direct in valid_ids:
        return direct
    if len(valid_ids) == 1:
        return next(iter(valid_ids))
    relation_ids = set(dedupe_preserve(relation.get('comparison_ids', [])) + dedupe_preserve(relation.get('excluded_or_absorbed_ids', [])) + dedupe_preserve(relation.get('source_task2_ids', [])))
    scored = []
    for final in finals:
        gold_id = str(final.get('gold_id', '')).strip()
        overlap = len(relation_ids & set(dedupe_preserve(final.get('source_task2_ids', []))))
        if gold_id and overlap:
            scored.append((overlap, gold_id))
    scored.sort(reverse=True)
    if scored and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        return scored[0][1]
    return ''

def _infer_relation_type(processing_result: str, rationale_text: str, comparison_ids: list[str], excluded_ids: list[str]) -> str:
    basis = str(rationale_text or '').lower()
    if processing_result == 'ABSORBED' or excluded_ids or any(word in basis for word in ('상위', '하위', '흡수', '포괄', 'parent', 'child')):
        return 'PARENT_CHILD'
    if any(word in basis for word in ('부분', '일부 중복', '고유 조건', 'partial', 'overlap')):
        return 'PARTIAL_OVERLAP'
    if processing_result == 'MERGED':
        return 'SEMANTIC_DUPLICATE'
    if processing_result == 'SEPARATED':
        return 'RELATED_DISTINCT'
    return 'UNIQUE' if len(comparison_ids) <= 1 else 'RELATED_DISTINCT'

def _default_relation_rationale(processing_result: str) -> str:
    messages = {
        'MERGED': '후보 요구사항의 의미 중복 또는 부분 중복을 통합하고 원문 조건을 보존하였다.',
        'ABSORBED': '상위·하위 또는 포함 관계를 기준으로 상세 요구사항에 흡수하였다.',
        'SEPARATED': '관련성은 있으나 수행행위 또는 검수 결과가 달라 별도 요구사항으로 유지하였다.',
        'KEPT': '독립 요구사항으로 판단하여 기존 내용을 유지하였다.',
    }
    return messages.get(processing_result, '후보 요구사항과 최종 GOLD의 관계를 기준으로 처리하였다.')

def _is_task3_final_like(item: dict) -> bool:
    return (
        isinstance(item, dict)
        and str(item.get('gold_id', '')).strip()
        and str(item.get('requirement_name', '')).strip()
        and str(item.get('requirement_detail', '')).strip()
        and isinstance(item.get('source_task2_ids'), list)
    )

def repair_task3_relation_metadata(obj: dict, repairs: list[str]) -> None:
    """기존 TASK3 학습 출력의 축약 relation_decisions를 결정적으로 보완한다.

    최종 GOLD 본문과 source_task2_ids는 변경하지 않고 감사용 관계 메타데이터만 보완한다.
    안전하게 추론할 수 없는 gold_id는 채우지 않아 이후 엄격 검증과 재시도가 동작하게 한다.
    """
    finals = [item for item in obj.get('final_requirements', []) if isinstance(item, dict)]
    final_by_gold = {str(item.get('gold_id', '')).strip(): item for item in finals if str(item.get('gold_id', '')).strip()}
    relations = obj.get('relation_decisions', [])
    if not isinstance(relations, list):
        return
    for index, relation in enumerate(relations):
        if not isinstance(relation, dict):
            continue
        prefix = f'relation_decisions[{index}]'
        if not relation.get('comparison_ids'):
            alias_ids = relation.get('source_task2_ids') or relation.get('candidate_ids') or relation.get('input_ids') or []
            relation['comparison_ids'] = dedupe_preserve(alias_ids)
            if relation['comparison_ids']:
                repairs.append(f'{prefix}.comparison_ids<-alias')
        relation['comparison_ids'] = dedupe_preserve(relation.get('comparison_ids', []))
        if not relation.get('excluded_or_absorbed_ids'):
            alias_ids = relation.get('absorbed_ids') or relation.get('excluded_ids') or []
            relation['excluded_or_absorbed_ids'] = dedupe_preserve(alias_ids)
            if relation['excluded_or_absorbed_ids']:
                repairs.append(f'{prefix}.excluded_or_absorbed_ids<-alias')
        relation['excluded_or_absorbed_ids'] = dedupe_preserve(relation.get('excluded_or_absorbed_ids', []))
        preserved = relation.get('preserved_conditions', relation.get('conditions', []))
        relation['preserved_conditions'] = dedupe_preserve(preserved)
        gold_id = _infer_relation_gold_id(relation, finals)
        if gold_id and str(relation.get('gold_id', '')).strip() != gold_id:
            relation['gold_id'] = gold_id
            repairs.append(f'{prefix}.gold_id->{gold_id}')
        final = final_by_gold.get(str(relation.get('gold_id', '')).strip())
        if not relation['comparison_ids'] and final:
            relation['comparison_ids'] = dedupe_preserve(final.get('source_task2_ids', []))
            repairs.append(f'{prefix}.comparison_ids<-final.source_task2_ids')
        raw_result = _first_nonempty(relation, ('processing_result', 'result', 'decision', 'processing', 'decision_result'))
        if not raw_result and final:
            raw_result = str(final.get('processing_type', '')).strip()
        processing_result = _normalize_processing_result(raw_result)
        if not processing_result:
            processing_result = 'MERGED' if len(relation['comparison_ids']) > 1 else 'KEPT'
        if relation.get('processing_result') != processing_result:
            relation['processing_result'] = processing_result
            repairs.append(f'{prefix}.processing_result->{processing_result}')
        rationale = _first_nonempty(relation, ('rationale', 'reason', 'basis', 'decision_basis', 'merge_basis'))
        if not rationale and final:
            rationale = str(final.get('merge_basis', '')).strip()
        raw_type = _first_nonempty(relation, ('relation_type', 'type', 'relation', 'relation_kind', 'category'))
        relation_type = _normalize_relation_type(raw_type)
        if not relation_type:
            relation_type = _infer_relation_type(processing_result, rationale, relation['comparison_ids'], relation['excluded_or_absorbed_ids'])
        if relation.get('relation_type') != relation_type:
            relation['relation_type'] = relation_type
            repairs.append(f'{prefix}.relation_type->{relation_type}')
        if not rationale:
            rationale = _default_relation_rationale(processing_result)
        if relation.get('rationale') != rationale:
            relation['rationale'] = rationale
            repairs.append(f'{prefix}.rationale<-derived')

def normalize_task_output_shape(task_type: str, candidate: dict) -> tuple[dict, list[str]]:
    """
    모델의 의미 내용은 그대로 두고 단수/복수 키, 개수,
    일부 관계 메타데이터만 결정적으로 보정합니다.
    """
    if not isinstance(candidate, dict):
        return (candidate, [])
    obj = dict(candidate)
    repairs = []
    if task_type == TASK1:
        singular_key = 'atomic_requirement'
        array_key = 'atomic_requirements'
        count_key = 'decomposition_count'
    elif task_type == TASK2:
        singular_key = 'normalized_requirement'
        array_key = 'normalized_requirements'
        count_key = 'normalized_requirement_count'
    elif task_type == TASK3:
        singular_key = 'final_requirement'
        array_key = 'final_requirements'
        count_key = 'final_requirement_count'
    else:
        return (obj, repairs)
    current_items = obj.get(array_key)
    if not isinstance(current_items, list):
        singular_value = obj.get(singular_key)
        if isinstance(singular_value, dict):
            obj[array_key] = [dict(singular_value)]
            repairs.append(f'{singular_key}:dict->{array_key}:list')
        elif isinstance(singular_value, list):
            obj[array_key] = [dict(item) if isinstance(item, dict) else item for item in singular_value]
            repairs.append(f'{singular_key}:list->{array_key}:list')
    if task_type == TASK3:
        relations = obj.get('relation_decisions')
        if relations is None:
            obj['relation_decisions'] = []
            repairs.append('relation_decisions:none->list')
        elif isinstance(relations, dict):
            obj['relation_decisions'] = [dict(relations)]
            repairs.append('relation_decisions:dict->list')
        elif isinstance(relations, list):
            obj['relation_decisions'] = [dict(item) if isinstance(item, dict) else item for item in relations]
        if not isinstance(obj.get('final_requirements'), list) or not obj.get('final_requirements'):
            maybe_finals = obj.get('relation_decisions', [])
            if isinstance(maybe_finals, list) and maybe_finals:
                final_like = [item for item in maybe_finals if _is_task3_final_like(item)]
                relation_like = [item for item in maybe_finals if not _is_task3_final_like(item)]
                if final_like:
                    obj['final_requirements'] = [dict(item) for item in final_like]
                    obj['relation_decisions'] = [dict(item) if isinstance(item, dict) else item for item in relation_like]
                    if relation_like:
                        repairs.append('relation_decisions:mixed_final_like->final_requirements')
                    else:
                        repairs.append('relation_decisions:final_like->final_requirements')
        finals = obj.get('final_requirements')
        relations = obj.get('relation_decisions', [])
        if isinstance(finals, list) and len(finals) == 1 and isinstance(finals[0], dict):
            only_gold_id = str(finals[0].get('gold_id', '')).strip()
            if only_gold_id:
                for relation_index, relation in enumerate(relations):
                    if not isinstance(relation, dict):
                        continue
                    relation_gold_id = str(relation.get('gold_id', '')).strip()
                    if not relation_gold_id:
                        relation['gold_id'] = only_gold_id
                        repairs.append(f'relation_decisions[{relation_index}].gold_id->{only_gold_id}')
        for relation_index, relation in enumerate(relations):
            if not isinstance(relation, dict):
                continue
            relation['comparison_ids'] = dedupe_preserve(relation.get('comparison_ids', []))
            relation['excluded_or_absorbed_ids'] = dedupe_preserve(relation.get('excluded_or_absorbed_ids', []))
            preserved = relation.get('preserved_conditions')
            if isinstance(preserved, str):
                preserved = preserved.strip()
                relation['preserved_conditions'] = [preserved] if preserved else []
                repairs.append(f'relation_decisions[{relation_index}].preserved_conditions:str->list')
            elif preserved is None:
                relation['preserved_conditions'] = []
                repairs.append(f'relation_decisions[{relation_index}].preserved_conditions:none->list')
    if task_type == TASK3:
        repair_task3_relation_metadata(obj, repairs)
    items = obj.get(array_key)
    if isinstance(items, list):
        declared_count = obj.get(count_key)
        actual_count = len(items)
        if declared_count != actual_count:
            obj[count_key] = actual_count
            repairs.append(f'{count_key}:{declared_count}->{actual_count}')
    return (obj, repairs)

def extract_complete_task_json(text: str, task_type: str) -> tuple[dict, str]:
    from json_repair import repair_json
    raw = text.strip()
    cleaned = re.sub('^```(?:json)?\\s*', '', raw, flags=re.IGNORECASE)
    cleaned = re.sub('\\s*```$', '', cleaned).strip()
    schema = OUTPUT_SCHEMAS[task_type]
    array_key = schema['array_key']
    count_key = schema['count_key']
    candidates = []
    for candidate_text, mode in ((raw, 'strict'), (cleaned, 'code_fence_removed')):
        try:
            parsed = json.loads(candidate_text)
            if isinstance(parsed, dict):
                candidates.append((parsed, mode))
        except Exception:
            pass
    decoder = json.JSONDecoder()
    for match in re.finditer('\\{', cleaned):
        try:
            parsed, _ = decoder.raw_decode(cleaned[match.start():])
            if isinstance(parsed, dict):
                candidates.append((parsed, 'json_object_candidate'))
        except Exception:
            continue
    try:
        repaired = repair_json(cleaned, return_objects=True)
        if isinstance(repaired, dict):
            candidates.append((repaired, 'json_repair'))
    except Exception:
        pass
    valid = []
    for raw_candidate, mode in candidates:
        candidate, repairs = normalize_task_output_shape(task_type, raw_candidate)
        items = candidate.get(array_key)
        if not isinstance(items, list):
            continue
        score = 50
        if candidate.get('task_type') == task_type:
            score += 100
        if count_key and count_key in candidate:
            score += 10
        if task_type == TASK3 and isinstance(candidate.get('relation_decisions'), list):
            score += 20
        score += min(len(items), 100)
        parse_mode = mode
        if repairs:
            parse_mode = f'{mode}+shape_repair'
        valid.append((score, len(json.dumps(candidate, ensure_ascii=False)), candidate, parse_mode, repairs))
    if not valid:
        key_sets = [sorted(candidate.keys()) for candidate, _ in candidates[:20] if isinstance(candidate, dict)]
        raise ValueError(f'{task_type} 전체 JSON 객체를 찾지 못했습니다.\n- expected array: {array_key}\n- discovered keys: {key_sets}\n- raw prefix: {raw[:1000]}')
    valid.sort(key=lambda row: (row[0], row[1]), reverse=True)
    _, _, selected, parse_mode, selected_repairs = valid[0]
    if selected_repairs:
        print(f'[출력 구조 자동 보정] {task_type}: ' + '; '.join(selected_repairs), flush=True)
    return (selected, parse_mode)

def validate_task_output(task_type: str, obj: dict) -> dict:
    """출력 구조를 보정·검증하고 보정된 객체를 반환합니다."""
    if not isinstance(obj, dict):
        raise TypeError(f'{task_type} 출력이 JSON 객체가 아닙니다.')
    obj, repairs = normalize_task_output_shape(task_type, obj)
    if repairs:
        print(f'[검증 전 구조 자동 보정] {task_type}: ' + '; '.join(repairs), flush=True)
    schema = OUTPUT_SCHEMAS[task_type]
    array_key = schema['array_key']
    actual_task_type = obj.get('task_type')
    if actual_task_type is None:
        if isinstance(obj.get(array_key), list):
            obj['task_type'] = task_type
            print(f'[TASK 타입 자동 보정] -> {task_type}', flush=True)
        else:
            raise ValueError(f'task_type과 핵심 배열이 모두 누락되었습니다. expected={task_type}, array={array_key}, keys={sorted(obj.keys())}')
    elif actual_task_type != task_type:
        raise ValueError(f'TASK 타입 불일치: expected={task_type}, actual={actual_task_type}')
    items = obj.get(array_key)
    if not isinstance(items, list):
        raise TypeError(f'{task_type}.{array_key}는 배열이어야 합니다.')
    if not items:
        raise ValueError(f'{task_type}.{array_key}가 0건입니다.')
    id_key = {TASK1: 'atomic_id', TASK2: 'task2_id', TASK3: 'gold_id'}[task_type]
    seen_ids = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise TypeError(f'{task_type}.{array_key}[{index}]가 객체가 아닙니다.')
        missing = schema['item_keys'] - set(item)
        if missing:
            raise ValueError(f'{task_type}.{array_key}[{index}] 필수 필드 누락={sorted(missing)} / actual={sorted(item.keys())}')
        item_id = str(item.get(id_key, '')).strip()
        if not item_id:
            raise ValueError(f'{task_type}.{array_key}[{index}].{id_key}가 비어 있습니다.')
        if item_id in seen_ids:
            raise ValueError(f'{task_type} 중복 {id_key}: {item_id}')
        seen_ids.add(item_id)
        if task_type == TASK1:
            for key in ('action_type', 'output_name', 'source_text'):
                if not str(item.get(key, '')).strip():
                    raise ValueError(f'{item_id}.{key}가 비어 있습니다.')
        elif task_type == TASK2:
            item['merged_from'] = dedupe_preserve(item.get('merged_from', []))
            item['reference_context_ids'] = dedupe_preserve(item.get('reference_context_ids', []))
            item['source_requirement_ids'] = dedupe_preserve(item.get('source_requirement_ids', []))
            if not str(item.get('requirement_name', '')).strip():
                raise ValueError(f'{item_id}.requirement_name이 비어 있습니다.')
            if not str(item.get('requirement_detail', '')).strip():
                raise ValueError(f'{item_id}.requirement_detail이 비어 있습니다.')
        elif task_type == TASK3:
            item['source_task2_ids'] = dedupe_preserve(item.get('source_task2_ids', []))
            item['source_atomic_ids'] = dedupe_preserve(item.get('source_atomic_ids', []))
            item['sources'] = dedupe_preserve(item.get('sources', []))
            if not item['source_task2_ids']:
                raise ValueError(f'{item_id}.source_task2_ids가 비어 있습니다.')
            if not str(item.get('requirement_name', '')).strip():
                raise ValueError(f'{item_id}.requirement_name이 비어 있습니다.')
            if not str(item.get('requirement_detail', '')).strip():
                raise ValueError(f'{item_id}.requirement_detail이 비어 있습니다.')
    count_key = schema['count_key']
    if count_key:
        obj[count_key] = len(items)
    if task_type == TASK3:
        relations = obj.get('relation_decisions')
        if relations is None:
            relations = []
            obj['relation_decisions'] = relations
        elif not isinstance(relations, list):
            raise TypeError('TASK3.relation_decisions는 배열이어야 합니다.')
        final_gold_ids = {str(item['gold_id']).strip() for item in items}
        for relation_index, relation in enumerate(relations):
            if not isinstance(relation, dict):
                raise TypeError(f'TASK3.relation_decisions[{relation_index}]가 객체가 아닙니다.')
            missing = RELATION_REQUIRED_KEYS - set(relation)
            if missing:
                raise ValueError(f'TASK3.relation_decisions[{relation_index}] 필수 필드 누락={sorted(missing)}')
            relation['comparison_ids'] = dedupe_preserve(relation.get('comparison_ids', []))
            relation['excluded_or_absorbed_ids'] = dedupe_preserve(relation.get('excluded_or_absorbed_ids', []))
            relation['preserved_conditions'] = dedupe_preserve(relation.get('preserved_conditions', []))
            relation_type = str(relation.get('relation_type', '')).strip()
            processing_result = str(relation.get('processing_result', '')).strip()
            relation_gold_id = str(relation.get('gold_id', '')).strip()
            if relation_type not in ALLOWED_RELATION_TYPES:
                raise ValueError(f'허용되지 않은 relation_type: {relation_type}')
            if processing_result not in ALLOWED_PROCESSING_RESULTS:
                raise ValueError(f'허용되지 않은 processing_result: {processing_result}')
            if relation_gold_id not in final_gold_ids:
                raise ValueError(f'관계 판정이 존재하지 않는 GOLD를 참조합니다: {relation_gold_id}')
            if not str(relation.get('rationale', '')).strip():
                raise ValueError(f'relation_decisions[{relation_index}].rationale이 비어 있습니다.')
    return obj
