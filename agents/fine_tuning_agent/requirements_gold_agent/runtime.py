from __future__ import annotations

import gc
import os
import threading
import time
import traceback
from pathlib import Path
from typing import Any

os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.pop("HF_HUB_ENABLE_HF_TRANSFER", None)
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
os.environ.setdefault("HF_XET_HIGH_PERFORMANCE", "1")

import torch
from huggingface_hub import login

from .config import (
    ATTN_IMPLEMENTATION,
    BASE_MODEL,
    ENV_FILE,
    GENERATION_POLICY,
    GENERATION_SAFETY_MARGIN,
    MINIMUM_FREE_GPU_GB,
    MODEL_CONTEXT_LIMIT_FALLBACK,
    STAGE1_ADAPTER_REPO,
    STAGE3_ADAPTER_REPO,
    TASK1,
    TASK2,
    TASK3,
    USE_4BIT,
)
from .contracts import build_prompt_messages, get_training_contracts, normalize_messages
from .env_loader import PROJECT_ENV_FILE, load_runtime_env
from agents.fine_tuning_agent.requirements_gold_error_utils import (
    RequirementGoldError,
    build_retry_error_prompt,
    get_requirement_gold_error_code,
)
from .output_validation import extract_complete_task_json, validate_task_output
from .storage import dump_json


class ModelRuntime:
    """Load the base model once and switch adapters by task."""

    def __init__(self) -> None:
        self._load_lock = threading.Lock()
        self._generate_lock = threading.RLock()
        self._loaded = False
        self.hf_token: str | None = None
        self.processor: Any = None
        self.tokenizer: Any = None
        self.model: Any = None
        self.model_context_limit = MODEL_CONTEXT_LIMIT_FALLBACK

    @property
    def loaded(self) -> bool:
        return self._loaded

    def start(self) -> "ModelRuntime":
        if self._loaded:
            return self
        with self._load_lock:
            if self._loaded:
                return self
            loaded_env_file = load_runtime_env(ENV_FILE, override=False)
            self.hf_token = os.getenv("HF_TOKEN")
            if not self.hf_token:
                env_hint = ENV_FILE
                if loaded_env_file == PROJECT_ENV_FILE:
                    env_hint = f"{ENV_FILE} 또는 {PROJECT_ENV_FILE}"
                raise RequirementGoldError(
                    "REQUIREMENT_GOLD_HF_TOKEN_MISSING",
                    f"HF_TOKEN이 없습니다. 환경변수 또는 {env_hint}을 확인하세요.",
                )
            if not torch.cuda.is_available():
                raise RequirementGoldError(
                    "REQUIREMENT_GOLD_CUDA_UNAVAILABLE",
                    "CUDA GPU가 필요합니다.",
                )
            login(token=self.hf_token, add_to_git_credential=False)
            from peft import PeftModel
            from transformers import (
                AutoConfig,
                AutoProcessor,
                BitsAndBytesConfig,
                Qwen3VLForConditionalGeneration,
            )

            get_training_contracts(self.hf_token)
            self.processor = AutoProcessor.from_pretrained(BASE_MODEL, token=self.hf_token)
            self.tokenizer = self.processor.tokenizer
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            base_config = AutoConfig.from_pretrained(BASE_MODEL, token=self.hf_token)
            text_config = getattr(base_config, "text_config", base_config)
            self.model_context_limit = int(
                getattr(text_config, "max_position_embeddings", MODEL_CONTEXT_LIMIT_FALLBACK)
            )
            kwargs: dict[str, Any] = {
                "token": self.hf_token,
                "device_map": {"": 0},
                "attn_implementation": ATTN_IMPLEMENTATION,
                "low_cpu_mem_usage": True,
            }
            if USE_4BIT:
                kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch.bfloat16,
                    bnb_4bit_use_double_quant=True,
                )
            else:
                kwargs["torch_dtype"] = torch.bfloat16
            base_model = Qwen3VLForConditionalGeneration.from_pretrained(BASE_MODEL, **kwargs)
            self.model = PeftModel.from_pretrained(
                base_model,
                STAGE1_ADAPTER_REPO,
                adapter_name="stage1",
                token=self.hf_token,
                is_trainable=False,
                low_cpu_mem_usage=True,
                autocast_adapter_dtype=False,
            )
            self.model.eval()
            torch.backends.cuda.matmul.allow_tf32 = True
            self.model.generation_config.do_sample = False
            self.model.generation_config.temperature = None
            self.model.generation_config.top_p = None
            self.model.generation_config.top_k = None
            self.model.generation_config.pad_token_id = self.tokenizer.pad_token_id
            self.model.generation_config.eos_token_id = self.tokenizer.eos_token_id
            self._loaded = True
        return self

    def _ensure_stage3(self) -> None:
        self.start()
        if "stage3" not in self.model.peft_config:
            self.model.load_adapter(
                STAGE3_ADAPTER_REPO,
                adapter_name="stage3",
                token=self.hf_token,
                is_trainable=False,
                low_cpu_mem_usage=True,
                autocast_adapter_dtype=False,
            )

    def _select_adapter(self, task_type: str) -> str:
        self.start()
        if task_type in {TASK1, TASK2}:
            self.model.set_adapter("stage1")
            return "stage1"
        if task_type == TASK3:
            self._ensure_stage3()
            self.model.set_adapter("stage3")
            return "stage3"
        raise ValueError(f"지원하지 않는 task_type: {task_type}")

    def _tokenize(self, messages: list[dict]) -> dict[str, torch.Tensor]:
        normalized = normalize_messages(messages, require_assistant=False)
        inputs = self.tokenizer.apply_chat_template(
            normalized,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        )
        inputs.pop("token_type_ids", None)
        return inputs

    def _gpu_status(self) -> dict[str, Any]:
        free_b, total_b = torch.cuda.mem_get_info()
        return {
            "device": torch.cuda.get_device_name(0),
            "free_gb": round(free_b / 1024**3, 2),
            "used_gb": round((total_b - free_b) / 1024**3, 2),
            "total_gb": round(total_b / 1024**3, 2),
        }

    def _max_new_tokens(
        self,
        task_type: str,
        prompt_tokens: int,
        explicit_cap: int | None = None,
    ) -> int:
        policy = GENERATION_POLICY[task_type]
        estimated = int(
            explicit_cap if explicit_cap is not None else prompt_tokens * float(policy["multiplier"])
        )
        estimated = max(estimated, int(policy["minimum"]))
        estimated = min(estimated, int(policy["maximum"]))
        actual = min(
            estimated,
            self.model_context_limit - prompt_tokens - GENERATION_SAFETY_MARGIN,
        )
        if actual < 1:
            raise RequirementGoldError(
                "REQUIREMENT_GOLD_CONTEXT_LIMIT_EXCEEDED",
                f"{task_type}: context limit 초과. prompt={prompt_tokens:,}",
            )
        return int(actual)

    @torch.inference_mode()
    def run_task(
        self,
        task_type: str,
        user_obj: dict[str, Any],
        *,
        raw_log_path: Path | None = None,
    ) -> tuple[dict[str, Any], str]:
        if user_obj.get("task_type") != task_type:
            raise ValueError(f"task_type 불일치: {task_type} != {user_obj.get('task_type')}")
        self.start()
        with self._generate_lock:
            adapter_name = self._select_adapter(task_type)
            prompt_messages = build_prompt_messages(task_type, user_obj, self.hf_token or "")
            policy = GENERATION_POLICY[task_type]
            max_attempts = int(policy["max_attempts"])
            base_messages = list(prompt_messages)
            current_messages = list(base_messages)
            explicit_cap: int | None = None
            attempts: list[dict[str, Any]] = []
            last_error: Exception | None = None
            raw_log_path = Path(raw_log_path) if raw_log_path else None
            if raw_log_path:
                raw_log_path.parent.mkdir(parents=True, exist_ok=True)

            for attempt in range(1, max_attempts + 1):
                generated = generated_ids = None
                inputs: dict[str, torch.Tensor] = {}
                cpu_inputs: dict[str, torch.Tensor] = {}
                raw_text = ""
                hit_token_limit = False
                try:
                    gc.collect()
                    torch.cuda.empty_cache()
                    cpu_inputs = self._tokenize(current_messages)
                    prompt_tokens = int(cpu_inputs["input_ids"].shape[-1])
                    max_new_tokens = self._max_new_tokens(task_type, prompt_tokens, explicit_cap)
                    status = self._gpu_status()
                    if status["free_gb"] < MINIMUM_FREE_GPU_GB:
                        raise RequirementGoldError(
                            "REQUIREMENT_GOLD_GPU_MEMORY_LOW",
                            f"{task_type}: GPU 여유 메모리 부족. free={status['free_gb']:.2f}GB",
                        )
                    inputs = {
                        key: value.to(self.model.device)
                        for key, value in cpu_inputs.items()
                        if isinstance(value, torch.Tensor)
                    }
                    input_length = int(inputs["input_ids"].shape[-1])
                    started = time.perf_counter()
                    generated = self.model.generate(
                        **inputs,
                        max_new_tokens=max_new_tokens,
                        do_sample=False,
                        use_cache=True,
                        eos_token_id=self.tokenizer.eos_token_id,
                        pad_token_id=self.tokenizer.pad_token_id,
                    )
                    elapsed = time.perf_counter() - started
                    generated_ids = generated[0, input_length:]
                    generated_count = int(generated_ids.shape[-1])
                    raw_text = self.tokenizer.decode(
                        generated_ids,
                        skip_special_tokens=True,
                        clean_up_tokenization_spaces=False,
                    ).strip()
                    hit_token_limit = generated_count >= max_new_tokens
                    record = {
                        "attempt": attempt,
                        "adapter_name": adapter_name,
                        "prompt_tokens": prompt_tokens,
                        "max_new_tokens": max_new_tokens,
                        "generated_tokens": generated_count,
                        "hit_token_limit": hit_token_limit,
                        "elapsed_seconds": elapsed,
                        "raw_text": raw_text,
                    }
                    if raw_log_path:
                        dump_json(
                            raw_log_path.with_name(f"{raw_log_path.stem}_attempt{attempt}.json"),
                            {"task_type": task_type, "user": user_obj, **record},
                        )
                    if hit_token_limit:
                        raise RequirementGoldError(
                            "REQUIREMENT_GOLD_OUTPUT_TRUNCATED",
                            f"{task_type}: 생성 토큰 한도 도달",
                        )
                    obj, parse_mode = extract_complete_task_json(raw_text, task_type)
                    if parse_mode.startswith("json_repair") and not raw_text.rstrip().endswith("}"):
                        raise RequirementGoldError(
                            "REQUIREMENT_GOLD_OUTPUT_INVALID",
                            f"{task_type}: 불완전 json_repair 결과 거부",
                        )
                    obj = validate_task_output(task_type, obj)
                    record["parse_mode"] = parse_mode
                    record["prediction"] = obj
                    attempts.append(record)
                    if raw_log_path:
                        dump_json(
                            raw_log_path,
                            {
                                "status": "SUCCESS",
                                "task_type": task_type,
                                "adapter_name": adapter_name,
                                "user": user_obj,
                                "attempts": attempts,
                                "prediction": obj,
                            },
                        )
                    return obj, raw_text
                except Exception as exc:
                    last_error = exc
                    traceback_text = traceback.format_exc()
                    attempts.append(
                        {
                            "attempt": attempt,
                            "error_code": get_requirement_gold_error_code(exc),
                            "error_type": type(exc).__name__,
                            "error_message": str(exc),
                            "traceback": traceback_text,
                            "hit_token_limit": hit_token_limit,
                        }
                    )
                    if attempt < max_attempts:
                        previous = locals().get("max_new_tokens", int(policy["minimum"]))
                        explicit_cap = min(
                            int(previous * float(policy["retry_growth"])),
                            int(policy["maximum"]),
                        )
                        error_context = build_retry_error_prompt(
                            exc,
                            traceback_text,
                            limit=1500,
                        )
                        current_messages = base_messages + [
                            {
                                "role": "user",
                                "content": (
                                    "직전 출력은 JSON 검증에 실패했습니다. 설명 없이 학습된 출력 "
                                    "스키마의 완전한 JSON 객체 하나만 다시 출력하라.\n"
                                    f"오류 로그:\n{error_context}"
                                ),
                            }
                        ]
                        continue
                    if raw_log_path:
                        dump_json(
                            raw_log_path.with_name(raw_log_path.stem + "_FAILED.json"),
                            {
                                "status": "FAILED",
                                "task_type": task_type,
                                "adapter_name": adapter_name,
                                "user": user_obj,
                                "attempts": attempts,
                            },
                        )
                    raise
                finally:
                    for value in (generated, generated_ids):
                        if value is not None:
                            del value
                    inputs.clear()
                    cpu_inputs.clear()
                    gc.collect()
                    torch.cuda.empty_cache()

            raise RequirementGoldError(
                "REQUIREMENT_GOLD_RETRY_EXHAUSTED",
                f"{task_type}: 재시도 모두 실패",
            ) from last_error


_runtime = ModelRuntime()


def get_runtime() -> ModelRuntime:
    return _runtime
