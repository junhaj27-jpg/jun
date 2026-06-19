from __future__ import annotations

import os
from pathlib import Path

TASK1 = "TASK1_FUR_ATOMIC_DECOMPOSITION"
TASK2 = "TASK2_FUR_LOCAL_MERGE_NORMALIZE"
TASK3 = "TASK3_DOCUMENT_GLOBAL_DEDUP_FINALIZE"
PIPELINE_VERSION = "gold-agent-v1.0-v10.5-core-no-eval"

HF_DATASET_REPO = os.getenv("REQ_HF_DATASET_REPO", "jaehoony/requirements-4task-dataset")
BASE_MODEL = os.getenv("REQ_BASE_MODEL", "Qwen/Qwen3-VL-8B-Instruct")
STAGE1_ADAPTER_REPO = os.getenv("REQ_STAGE1_ADAPTER_REPO", "jaehoony/req-qwen3vl-stage1-core")
STAGE3_ADAPTER_REPO = os.getenv("REQ_STAGE3_ADAPTER_REPO", "jaehoony/req-qwen3vl-stage3-task3doc")
OUTPUT_DIR = Path(os.getenv("REQ_AGENT_OUTPUT_DIR", "/workspace/requirements_gold_agent_outputs"))
ENV_FILE = os.getenv("REQ_ENV_FILE", "/workspace/env")

ATTN_IMPLEMENTATION = os.getenv("REQ_ATTN_IMPLEMENTATION", "sdpa")
USE_4BIT = os.getenv("REQ_USE_4BIT", "0") == "1"
MODEL_CONTEXT_LIMIT_FALLBACK = int(os.getenv("REQ_CONTEXT_LIMIT_FALLBACK", "262144"))
GENERATION_SAFETY_MARGIN = int(os.getenv("REQ_GENERATION_SAFETY_MARGIN", "2048"))
MINIMUM_FREE_GPU_GB = float(os.getenv("REQ_MINIMUM_FREE_GPU_GB", "8.0"))
GENERATION_POLICY = {
    TASK1: {"multiplier": 1.5, "minimum": 4096, "maximum": 8192, "retry_growth": 1.5, "max_attempts": 2},
    TASK2: {"multiplier": 1.5, "minimum": 6144, "maximum": 12288, "retry_growth": 1.5, "max_attempts": 2},
    TASK3: {"multiplier": 1.5, "minimum": 2048, "maximum": 12288, "retry_growth": 1.5, "max_attempts": 2},
}

EMBEDDING_MODEL_NAME = os.getenv("REQ_EMBEDDING_MODEL", "intfloat/multilingual-e5-base")
EMBEDDING_DEVICE = os.getenv("REQ_EMBEDDING_DEVICE", "cuda")
EMBEDDING_BATCH_SIZE = int(os.getenv("REQ_EMBEDDING_BATCH_SIZE", "64"))
HIGH_SIM_THRESHOLD = float(os.getenv("REQ_HIGH_SIM_THRESHOLD", "0.92"))
REVIEW_SIM_THRESHOLD = float(os.getenv("REQ_REVIEW_SIM_THRESHOLD", "0.86"))
ADAPTIVE_FLOOR_MAX = float(os.getenv("REQ_ADAPTIVE_FLOOR_MAX", "0.91"))
NAME_JACCARD_THRESHOLD = float(os.getenv("REQ_NAME_JACCARD_THRESHOLD", "0.12"))
LEXICAL_COSINE_THRESHOLD = float(os.getenv("REQ_LEXICAL_COSINE_THRESHOLD", "0.82"))
LEXICAL_NAME_JACCARD_THRESHOLD = float(os.getenv("REQ_LEXICAL_NAME_JACCARD_THRESHOLD", "0.40"))
PAIR_SIMILARITY_QUANTILE = float(os.getenv("REQ_PAIR_SIMILARITY_QUANTILE", "0.97"))
MUTUAL_TOP_K = int(os.getenv("REQ_MUTUAL_TOP_K", "5"))
GROUP_MIN_PAIR_SIMILARITY = float(os.getenv("REQ_GROUP_MIN_PAIR_SIMILARITY", "0.84"))
TASK3_MAX_GROUP_SIZE = int(os.getenv("REQ_TASK3_MAX_GROUP_SIZE", "8"))
TASK3_MAX_LOCAL_ROUNDS = int(os.getenv("REQ_TASK3_MAX_LOCAL_ROUNDS", "3"))
SCOPE_TOP_K = int(os.getenv("REQ_SCOPE_TOP_K", "3"))
SCOPE_SIM_THRESHOLD = float(os.getenv("REQ_SCOPE_SIM_THRESHOLD", "0.78"))
TASK3_COVERAGE_FALLBACK_ENABLED = os.getenv("REQ_TASK3_COVERAGE_FALLBACK", "1") == "1"
APPLY_GLOBAL_SCOPE_TO_SINGLETONS = os.getenv("REQ_APPLY_GLOBAL_SCOPE_SINGLETONS", "1") == "1"

JSON_WRITE_RETRY_COUNT = int(os.getenv("REQ_JSON_WRITE_RETRY_COUNT", "5"))
JSON_WRITE_RETRY_SECONDS = float(os.getenv("REQ_JSON_WRITE_RETRY_SECONDS", "1.0"))

TASK_SEARCH_FOLDERS = {TASK1: ["stage1_core"], TASK2: ["stage1_core"], TASK3: ["stage3_task3_doc"]}
TASK_ARRAY_KEYS = {TASK1: "atomic_requirements", TASK2: "normalized_requirements", TASK3: "final_requirements"}
OUTPUT_SCHEMAS = {
    TASK1: {"array_key": "atomic_requirements", "count_key": "decomposition_count", "item_keys": {"atomic_id", "action_type", "output_name", "source_text"}},
    TASK2: {"array_key": "normalized_requirements", "count_key": "normalized_requirement_count", "item_keys": {"task2_id", "merge_decision", "merged_from", "reference_context_ids", "action_type", "requirement_name", "requirement_detail", "source_requirement_ids"}},
    TASK3: {"array_key": "final_requirements", "count_key": "final_requirement_count", "item_keys": {"gold_id", "action_type", "requirement_name", "requirement_detail", "source_task2_ids", "source_atomic_ids", "sources", "processing_type", "merge_basis"}},
}
