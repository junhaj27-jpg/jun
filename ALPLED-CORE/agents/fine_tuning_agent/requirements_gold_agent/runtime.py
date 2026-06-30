from __future__ import annotations

import json
import os
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from tools.llm.llm_client import LLMClient

from .config import (
    ENV_FILE,
    GENERATION_POLICY,
    GENERATION_SAFETY_MARGIN,
    MODEL_CONTEXT_LIMIT_FALLBACK,
    STAGE1_SERVED_MODEL,
    STAGE3_SERVED_MODEL,
    TASK1,
    TASK2,
    TASK3,
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
    """Run requirements Gold tasks through LoRA adapters served by vLLM."""

    def __init__(self) -> None:
        self._load_lock = threading.Lock()
        self._generate_lock = threading.RLock()
        self._loaded = False
        self.hf_token: str | None = None
        self.model_context_limit = MODEL_CONTEXT_LIMIT_FALLBACK
        self._clients: dict[str, LLMClient] = {}

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

            # 학습 데이터셋에서 사용하던 system prompt 계약은 그대로 유지합니다.
            get_training_contracts(self.hf_token)
            self.model_context_limit = int(
                os.getenv(
                    "REQ_VLLM_CONTEXT_LIMIT",
                    str(MODEL_CONTEXT_LIMIT_FALLBACK),
                )
            )
            self._clients = {
                "stage1": LLMClient(model_name=STAGE1_SERVED_MODEL),
                "stage3": LLMClient(model_name=STAGE3_SERVED_MODEL),
            }
            self._loaded = True
        return self

    def _select_adapter(self, task_type: str) -> str:
        self.start()
        if task_type in {TASK1, TASK2}:
            return "stage1"
        if task_type == TASK3:
            return "stage3"
        raise ValueError(f"지원하지 않는 task_type: {task_type}")

    @staticmethod
    def _estimate_prompt_tokens(messages: list[dict[str, Any]]) -> int:
        normalized = normalize_messages(messages, require_assistant=False)
        rendered = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
        # 한글/JSON 혼합 프롬프트에 보수적인 근사치를 사용합니다. 실제 한도는 vLLM도 검증합니다.
        return max(1, (len(rendered.encode("utf-8")) + 2) // 3)

    def _max_new_tokens(
        self,
        task_type: str,
        prompt_tokens: int,
        explicit_cap: int | None = None,
    ) -> int:
        policy = GENERATION_POLICY[task_type]
        estimated = int(
            explicit_cap
            if explicit_cap is not None
            else prompt_tokens * float(policy["multiplier"])
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

    @staticmethod
    def _completion(response: Any) -> tuple[str, int, str]:
        try:
            choice = response["choices"][0]
            message = choice["message"]
            raw_text = str(message.get("content") or "").strip()
            finish_reason = str(choice.get("finish_reason") or "")
            usage = response.get("usage") or {}
            generated_tokens = int(usage.get("completion_tokens") or 0)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RequirementGoldError(
                "REQUIREMENT_GOLD_VLLM_RESPONSE_INVALID",
                f"vLLM 응답 형식이 올바르지 않습니다: {exc}",
            ) from exc
        if not raw_text:
            raise RequirementGoldError(
                "REQUIREMENT_GOLD_VLLM_RESPONSE_EMPTY",
                "vLLM이 빈 응답을 반환했습니다.",
            )
        return raw_text, generated_tokens, finish_reason

    def run_task(
        self,
        task_type: str,
        user_obj: dict[str, Any],
        *,
        raw_log_path: Path | None = None,
    ) -> tuple[dict[str, Any], str]:
        if user_obj.get("task_type") != task_type:
            raise ValueError(
                f"task_type 불일치: {task_type} != {user_obj.get('task_type')}"
            )
        self.start()
        with self._generate_lock:
            adapter_name = self._select_adapter(task_type)
            client = self._clients[adapter_name]
            prompt_messages = build_prompt_messages(
                task_type,
                user_obj,
                self.hf_token or "",
            )
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
                raw_text = ""
                hit_token_limit = False
                try:
                    prompt_tokens = self._estimate_prompt_tokens(current_messages)
                    max_new_tokens = self._max_new_tokens(
                        task_type,
                        prompt_tokens,
                        explicit_cap,
                    )
                    started = time.perf_counter()
                    response = client.chat(
                        current_messages,
                        temperature=0.0,
                        max_tokens=max_new_tokens,
                        extra_body={
                            "response_format": {"type": "json_object"},
                        },
                    )
                    elapsed = time.perf_counter() - started
                    if not response["success"]:
                        error = response.get("error") or {}
                        raise RequirementGoldError(
                            "REQUIREMENT_GOLD_VLLM_REQUEST_FAILED",
                            str(error.get("message") or "vLLM 요청에 실패했습니다."),
                        )
                    raw_text, generated_count, finish_reason = self._completion(
                        response["data"]
                    )
                    hit_token_limit = finish_reason == "length"
                    record = {
                        "attempt": attempt,
                        "adapter_name": adapter_name,
                        "served_model_name": client.model_name,
                        "prompt_tokens_estimated": prompt_tokens,
                        "max_new_tokens": max_new_tokens,
                        "generated_tokens": generated_count,
                        "finish_reason": finish_reason,
                        "hit_token_limit": hit_token_limit,
                        "elapsed_seconds": elapsed,
                        "raw_text": raw_text,
                    }
                    if raw_log_path:
                        dump_json(
                            raw_log_path.with_name(
                                f"{raw_log_path.stem}_attempt{attempt}.json"
                            ),
                            {"task_type": task_type, "user": user_obj, **record},
                        )
                    if hit_token_limit:
                        raise RequirementGoldError(
                            "REQUIREMENT_GOLD_OUTPUT_TRUNCATED",
                            f"{task_type}: 생성 토큰 한도 도달",
                        )
                    obj, parse_mode = extract_complete_task_json(raw_text, task_type)
                    if parse_mode.startswith("json_repair") and not raw_text.rstrip().endswith(
                        "}"
                    ):
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
                                "served_model_name": client.model_name,
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
                            "adapter_name": adapter_name,
                            "served_model_name": client.model_name,
                            "error_code": get_requirement_gold_error_code(exc),
                            "error_type": type(exc).__name__,
                            "error_message": str(exc),
                            "traceback": traceback_text,
                            "hit_token_limit": hit_token_limit,
                        }
                    )
                    if attempt < max_attempts:
                        previous = locals().get(
                            "max_new_tokens",
                            int(policy["minimum"]),
                        )
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
                                "served_model_name": client.model_name,
                                "user": user_obj,
                                "attempts": attempts,
                            },
                        )
                    raise

            raise RequirementGoldError(
                "REQUIREMENT_GOLD_RETRY_EXHAUSTED",
                f"{task_type}: 재시도 모두 실패",
            ) from last_error


_runtime = ModelRuntime()


def get_runtime() -> ModelRuntime:
    return _runtime
