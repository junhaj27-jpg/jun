from __future__ import annotations

from pathlib import Path

from .config import TASK1
from .runtime import get_runtime

def normalize_atomic_ids(source_fur_id: str, atomics: list[dict]) -> list[dict]:
    normalized = []
    seen = set()
    for index, raw_item in enumerate(atomics, start=1):
        item = dict(raw_item)
        current_atomic_id = str(item.get('atomic_id', '')).strip() or f'A-{index:03d}'
        original_atomic_id = str(item.get('original_atomic_id', current_atomic_id.split('::')[-1])).strip() or f'A-{index:03d}'
        global_atomic_id = f'{source_fur_id}::{original_atomic_id}'
        if global_atomic_id in seen:
            raise ValueError(f'TASK1 중복 atomic_id: {global_atomic_id}')
        seen.add(global_atomic_id)
        item['original_atomic_id'] = original_atomic_id
        item['atomic_id'] = global_atomic_id
        item['source_fur_id'] = source_fur_id
        normalized.append(item)
    return normalized

def validate_task1_result(source_fur_id: str, atomics: list[dict]) -> None:
    if not atomics:
        raise ValueError(f'{source_fur_id}: TASK1 결과가 0건입니다.')
    seen = set()
    for index, item in enumerate(atomics):
        atomic_id = str(item.get('atomic_id', '')).strip()
        if not atomic_id:
            raise ValueError(f'{source_fur_id}: atomic[{index}] ID 누락')
        if atomic_id in seen:
            raise ValueError(f'{source_fur_id}: 중복 atomic_id={atomic_id}')
        seen.add(atomic_id)
        if item.get('source_fur_id') != source_fur_id:
            raise ValueError(f'{atomic_id}: source_fur_id 불일치')
        for key in ('action_type', 'output_name', 'source_text'):
            if not str(item.get(key, '')).strip():
                raise ValueError(f'{atomic_id}.{key}가 비어 있습니다.')

def stage_task1(doc_id: str, doc_name: str, fur: dict, *, raw_log_path: Path) -> list[dict]:
    required = {'requirement_id', 'requirement_name', 'requirement_type', 'requirement_definition', 'requirement_detail'}
    missing = required - set(fur)
    if missing:
        raise ValueError(f'TASK1 입력 필드 누락: {sorted(missing)}')
    user_obj = {'task_type': TASK1, 'document_id': doc_id, 'document_name': doc_name, 'requirement': fur}
    obj, _ = get_runtime().run_task(TASK1, user_obj, raw_log_path=raw_log_path)
    source_fur_id = str(fur['requirement_id']).strip()
    atomics = normalize_atomic_ids(source_fur_id, obj['atomic_requirements'])
    validate_task1_result(source_fur_id, atomics)
    return atomics
