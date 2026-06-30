from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
import torch
from .config import (ADAPTIVE_FLOOR_MAX, EMBEDDING_BATCH_SIZE, EMBEDDING_DEVICE, EMBEDDING_MODEL_NAME, GROUP_MIN_PAIR_SIMILARITY, HIGH_SIM_THRESHOLD, LEXICAL_COSINE_THRESHOLD, LEXICAL_NAME_JACCARD_THRESHOLD, MUTUAL_TOP_K, NAME_JACCARD_THRESHOLD, PAIR_SIMILARITY_QUANTILE, REVIEW_SIM_THRESHOLD, SCOPE_SIM_THRESHOLD, SCOPE_TOP_K, TASK3_MAX_GROUP_SIZE)
from .storage import dump_json, write_csv
from .utils import dedupe_preserve

TOKEN_PATTERN = re.compile(r"[가-힣A-Za-z0-9]+")
_embedding_model = None

def get_embedding_model():
    global _embedding_model
    from sentence_transformers import SentenceTransformer
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME, device=EMBEDDING_DEVICE)
    return _embedding_model

def text_tokens(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_PATTERN.findall(str(text)) if len(token) >= 2}

def jaccard(text_a: str, text_b: str) -> float:
    tokens_a = text_tokens(text_a)
    tokens_b = text_tokens(text_b)
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)

def source_overlap(left: dict, right: dict) -> bool:
    """
    출처 중첩은 분석용 메타데이터로만 사용합니다.
    같은 FUR 출처라는 이유만으로 유사 그룹을 연결하지 않습니다.
    """
    return bool(set(left.get('source_requirement_ids', [])) & set(right.get('source_requirement_ids', [])))

def embedding_text(item: dict) -> str:
    return f"query: 수행행위: {item.get('action_type', '미지정')}\n요구사항명: {item.get('requirement_name', '')}\n상세내용: {item.get('requirement_detail', '')}"

def similarity_distribution(matrix: np.ndarray) -> dict:
    size = int(matrix.shape[0])
    if size < 2:
        return {'pair_count': 0, 'min': None, 'q50': None, 'q75': None, 'q90': None, 'q95': None, 'q97': None, 'q99': None, 'max': None}
    upper = matrix[np.triu_indices(size, k=1)]
    return {'pair_count': int(upper.size), 'min': round(float(np.min(upper)), 6), 'q50': round(float(np.quantile(upper, 0.5)), 6), 'q75': round(float(np.quantile(upper, 0.75)), 6), 'q90': round(float(np.quantile(upper, 0.9)), 6), 'q95': round(float(np.quantile(upper, 0.95)), 6), 'q97': round(float(np.quantile(upper, 0.97)), 6), 'q99': round(float(np.quantile(upper, 0.99)), 6), 'max': round(float(np.max(upper)), 6)}

def mutual_top_k_sets(similarity_matrix: np.ndarray, top_k: int) -> list[set[int]]:
    size = int(similarity_matrix.shape[0])
    result = []
    for index in range(size):
        scores = similarity_matrix[index].astype(float).copy()
        scores[index] = -np.inf
        count = min(max(int(top_k), 1), max(size - 1, 0))
        if count == 0:
            result.append(set())
            continue
        neighbor_indices = np.argsort(-scores)[:count]
        result.append({int(value) for value in neighbor_indices if np.isfinite(scores[int(value)])})
    return result

def all_cross_pairs_above(left_group: set[int], right_group: set[int], similarity_matrix: np.ndarray, minimum: float) -> bool:
    for left in left_group:
        for right in right_group:
            if float(similarity_matrix[left, right]) < minimum:
                return False
    return True

def complete_link_groups(item_count: int, eligible_edges: list[dict], similarity_matrix: np.ndarray, max_group_size: int, minimum_pair_similarity: float) -> tuple[list[list[int]], list[int]]:
    """
    높은 점수의 쌍부터 그룹을 만들되,
    그룹에 새 항목을 추가하거나 두 그룹을 합칠 때
    모든 교차 쌍이 minimum 이상인지 확인합니다.

    단순 연결 전이로 거대 컴포넌트가 만들어지지 않습니다.
    """
    groups: list[set[int]] = []
    item_to_group: dict[int, int] = {}
    sorted_edges = sorted(eligible_edges, key=lambda row: (row['cosine_similarity'], row['name_jaccard']), reverse=True)
    for edge in sorted_edges:
        left = int(edge['left_index'])
        right = int(edge['right_index'])
        left_group_no = item_to_group.get(left)
        right_group_no = item_to_group.get(right)
        if left_group_no is None and right_group_no is None:
            if float(similarity_matrix[left, right]) >= minimum_pair_similarity:
                group_no = len(groups)
                groups.append({left, right})
                item_to_group[left] = group_no
                item_to_group[right] = group_no
            continue
        if left_group_no is not None and left_group_no == right_group_no:
            continue
        if left_group_no is not None and right_group_no is None:
            group = groups[left_group_no]
            if len(group) + 1 <= max_group_size and all_cross_pairs_above(group, {right}, similarity_matrix, minimum_pair_similarity):
                group.add(right)
                item_to_group[right] = left_group_no
            continue
        if left_group_no is None and right_group_no is not None:
            group = groups[right_group_no]
            if len(group) + 1 <= max_group_size and all_cross_pairs_above({left}, group, similarity_matrix, minimum_pair_similarity):
                group.add(left)
                item_to_group[left] = right_group_no
            continue
        if left_group_no is not None and right_group_no is not None and (left_group_no != right_group_no):
            left_group = groups[left_group_no]
            right_group = groups[right_group_no]
            if not left_group or not right_group:
                continue
            if len(left_group) + len(right_group) <= max_group_size and all_cross_pairs_above(left_group, right_group, similarity_matrix, minimum_pair_similarity):
                merged = left_group | right_group
                groups[left_group_no] = merged
                groups[right_group_no] = set()
                for item_index in merged:
                    item_to_group[item_index] = left_group_no
    similar_groups = [sorted(group) for group in groups if len(group) >= 2]
    similar_groups.sort(key=lambda group: min(group))
    grouped_indices = {index for group in similar_groups for index in group}
    singleton_indices = [index for index in range(item_count) if index not in grouped_indices]
    return (similar_groups, singleton_indices)

def build_similarity_groups(doc_id: str, candidates: list[dict], output_dir: Path) -> dict:
    if not candidates:
        raise ValueError('임베딩 후보가 0건입니다.')
    model_for_embedding = get_embedding_model()
    texts = [embedding_text(item) for item in candidates]
    embeddings = model_for_embedding.encode(texts, batch_size=EMBEDDING_BATCH_SIZE, show_progress_bar=True, normalize_embeddings=True, convert_to_numpy=True)
    similarity_matrix = embeddings @ embeddings.T
    distribution = similarity_distribution(similarity_matrix)
    if len(candidates) >= 2:
        upper = similarity_matrix[np.triu_indices(len(candidates), k=1)]
        adaptive_floor = min(max(float(REVIEW_SIM_THRESHOLD), float(np.quantile(upper, PAIR_SIMILARITY_QUANTILE))), float(ADAPTIVE_FLOOR_MAX))
    else:
        adaptive_floor = float(REVIEW_SIM_THRESHOLD)
    top_k_sets = mutual_top_k_sets(similarity_matrix, MUTUAL_TOP_K)
    all_pairs = []
    eligible_edges = []
    for left_index in range(len(candidates)):
        for right_index in range(left_index + 1, len(candidates)):
            left = candidates[left_index]
            right = candidates[right_index]
            cosine = float(similarity_matrix[left_index, right_index])
            same_action = left.get('action_type') == right.get('action_type')
            overlap_source = source_overlap(left, right)
            name_overlap = jaccard(left.get('requirement_name', ''), right.get('requirement_name', ''))
            mutual_neighbor = right_index in top_k_sets[left_index] and left_index in top_k_sets[right_index]
            high_match = cosine >= HIGH_SIM_THRESHOLD
            evidence_match = mutual_neighbor and cosine >= adaptive_floor and (same_action or name_overlap >= NAME_JACCARD_THRESHOLD)
            lexical_match = name_overlap >= LEXICAL_NAME_JACCARD_THRESHOLD and cosine >= LEXICAL_COSINE_THRESHOLD
            action_match = same_action and name_overlap >= NAME_JACCARD_THRESHOLD and (cosine >= REVIEW_SIM_THRESHOLD)
            connected = high_match or evidence_match or lexical_match or action_match
            reasons = []
            if high_match:
                reasons.append('MUTUAL_TOPK_HIGH_COSINE')
            if evidence_match:
                reasons.append('MUTUAL_TOPK_ADAPTIVE_WITH_EVIDENCE')
            if lexical_match:
                reasons.append('LEXICAL_NAME_OVERLAP')
            if action_match:
                reasons.append('ACTION_AND_NAME_EVIDENCE')
            record = {'left_index': left_index, 'right_index': right_index, 'left_id': left['task2_id'], 'right_id': right['task2_id'], 'cosine_similarity': round(cosine, 6), 'same_action_type': same_action, 'source_overlap': overlap_source, 'name_jaccard': round(name_overlap, 6), 'mutual_top_k': mutual_neighbor, 'adaptive_floor': round(adaptive_floor, 6), 'high_match': high_match, 'evidence_match': evidence_match, 'lexical_match': lexical_match, 'action_match': action_match, 'connect': connected, 'reason': reasons}
            all_pairs.append(record)
            if connected:
                eligible_edges.append(record)
    similar_components, singleton_indices = complete_link_groups(item_count=len(candidates), eligible_edges=eligible_edges, similarity_matrix=similarity_matrix, max_group_size=TASK3_MAX_GROUP_SIZE, minimum_pair_similarity=GROUP_MIN_PAIR_SIMILARITY)
    group_rows = []
    for group_no, component in enumerate(similar_components, start=1):
        pair_scores = [float(similarity_matrix[left, right]) for position, left in enumerate(component) for right in component[position + 1:]]
        group_rows.append({'group_no': group_no, 'group_type': 'SIMILAR', 'size': len(component), 'task2_ids': [candidates[index]['task2_id'] for index in component], 'min_pair_similarity': round(min(pair_scores), 6), 'average_pair_similarity': round(float(np.mean(pair_scores)), 6), 'max_pair_similarity': round(max(pair_scores), 6), 'exceeds_group_limit': False})
    for singleton_index in singleton_indices:
        group_rows.append({'group_no': None, 'group_type': 'SINGLETON', 'size': 1, 'task2_ids': [candidates[singleton_index]['task2_id']], 'min_pair_similarity': None, 'average_pair_similarity': None, 'max_pair_similarity': None, 'exceeds_group_limit': False})
    output_dir.mkdir(parents=True, exist_ok=True)
    dump_json(output_dir / '00_similarity_distribution.json', {'document_id': doc_id, 'candidate_count': len(candidates), 'distribution': distribution, 'adaptive_floor': round(adaptive_floor, 6), 'settings': {'high_similarity': HIGH_SIM_THRESHOLD, 'review_similarity': REVIEW_SIM_THRESHOLD, 'pair_quantile': PAIR_SIMILARITY_QUANTILE, 'mutual_top_k': MUTUAL_TOP_K, 'name_jaccard': NAME_JACCARD_THRESHOLD, 'lexical_cosine': LEXICAL_COSINE_THRESHOLD, 'lexical_name_jaccard': LEXICAL_NAME_JACCARD_THRESHOLD, 'adaptive_floor_max': ADAPTIVE_FLOOR_MAX, 'group_min_pair': GROUP_MIN_PAIR_SIMILARITY, 'max_group_size': TASK3_MAX_GROUP_SIZE}})
    dump_json(output_dir / '01_similarity_edges.json', {'document_id': doc_id, 'adaptive_floor': round(adaptive_floor, 6), 'connected_edges': eligible_edges})
    dump_json(output_dir / '02_similarity_groups.json', {'document_id': doc_id, 'candidate_count': len(candidates), 'similar_component_count': len(similar_components), 'similar_component_item_count': sum((len(component) for component in similar_components)), 'singleton_count': len(singleton_indices), 'groups': group_rows})
    write_csv(output_dir / '01_similarity_edges.csv', eligible_edges)
    write_csv(output_dir / '02_similarity_groups.csv', group_rows)
    print('=' * 72)
    print('[임베딩 유사 후보 검색 v10]')
    print('전체 TASK2 후보     :', len(candidates))
    print('유사도 분포 q95/q97 :', distribution['q95'], distribution['q97'])
    print('적응형 유사도 하한  :', round(adaptive_floor, 6))
    print('유효 유사 쌍        :', len(eligible_edges))
    print('유사 그룹           :', len(similar_components))
    print('유사 그룹 항목      :', sum((len(component) for component in similar_components)))
    print('독립 항목           :', len(singleton_indices))
    print('최대 그룹 크기      :', max((len(component) for component in similar_components), default=0))
    print('=' * 72)
    if similar_components and max((len(component) for component in similar_components)) > TASK3_MAX_GROUP_SIZE:
        raise RuntimeError('유사 그룹 최대 크기 제한이 적용되지 않았습니다.')
    return {'embeddings': embeddings, 'similarity_matrix': similarity_matrix, 'similar_components': similar_components, 'singleton_indices': singleton_indices, 'group_rows': group_rows, 'connected_edges': eligible_edges, 'similarity_distribution': distribution, 'adaptive_floor': adaptive_floor}

def split_indices_by_similarity(indices: list[int], similarity_matrix: np.ndarray, max_size: int) -> list[list[int]]:
    """
    v8 그룹은 이미 max_size 이하이지만,
    로컬 처리의 방어 로직으로 유지합니다.
    """
    if len(indices) <= max_size:
        return [sorted(indices)]
    remaining = set(indices)
    chunks = []
    while remaining:
        seed = max(remaining, key=lambda index: sum((float(similarity_matrix[index, other]) for other in remaining if other != index)))
        group = [seed]
        remaining.remove(seed)
        while remaining and len(group) < max_size:
            ranked = sorted(remaining, key=lambda index: min((float(similarity_matrix[index, member]) for member in group)), reverse=True)
            best = ranked[0]
            if min((float(similarity_matrix[best, member]) for member in group)) < GROUP_MIN_PAIR_SIMILARITY:
                break
            group.append(best)
            remaining.remove(best)
        chunks.append(sorted(group))
    return chunks

def scope_text(item: dict) -> str:
    return f"query: 요구사항명: {item.get('requirement_name', item.get('name', ''))}\n상세내용: {item.get('requirement_detail', item.get('description', ''))}"

def build_scope_embedding_cache(scope_reference_requirements: list[dict]) -> dict:
    valid = [dict(item) for item in scope_reference_requirements if isinstance(item, dict)]
    global_scope = [item for item in valid if item.get('global_scope') is True]
    local_scope = [item for item in valid if item.get('global_scope') is not True]
    if local_scope:
        local_vectors = get_embedding_model().encode([scope_text(item) for item in local_scope], batch_size=EMBEDDING_BATCH_SIZE, show_progress_bar=False, normalize_embeddings=True, convert_to_numpy=True)
    else:
        local_vectors = np.empty((0, 0), dtype=np.float32)
    return {'global_scope': global_scope, 'local_scope': local_scope, 'local_vectors': local_vectors}

def select_scope_for_group(group_candidates: list[dict], group_embeddings: np.ndarray, scope_cache: dict) -> list[dict]:
    global_scope = scope_cache.get('global_scope', [])
    local_scope = scope_cache.get('local_scope', [])
    scope_vectors = scope_cache.get('local_vectors')
    if not local_scope:
        return list(global_scope)
    group_vector = group_embeddings.mean(axis=0)
    norm = float(np.linalg.norm(group_vector))
    if norm > 0:
        group_vector = group_vector / norm
    scores = scope_vectors @ group_vector
    ranked = np.argsort(-scores)
    selected = []
    for scope_index in ranked[:SCOPE_TOP_K]:
        if float(scores[int(scope_index)]) >= SCOPE_SIM_THRESHOLD:
            selected.append(local_scope[int(scope_index)])
    return list(global_scope) + selected
