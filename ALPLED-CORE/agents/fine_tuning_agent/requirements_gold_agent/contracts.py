from __future__ import annotations

import json
import threading
from typing import Any

from .config import HF_DATASET_REPO, TASK_ARRAY_KEYS, TASK_SEARCH_FOLDERS

_contract_lock = threading.Lock()
_contracts: dict[str, dict] | None = None


def message_text(message: dict) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(item.get("text", "")) for item in content if isinstance(item, dict) and item.get("type") == "text")
    return str(content)


def normalize_messages(messages: list[dict], require_assistant: bool = False) -> list[dict]:
    normalized: list[dict] = []
    has_assistant = False
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if role not in {"system", "user", "assistant"}:
            raise ValueError(f"지원하지 않는 role: {role}")
        has_assistant = has_assistant or role == "assistant"
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        elif isinstance(content, list):
            clean = []
            for item in content:
                if not isinstance(item, dict) or item.get("type") != "text":
                    raise ValueError("이 파이프라인은 text content만 지원합니다.")
                clean.append({"type": "text", "text": str(item.get("text", ""))})
            content = clean
        else:
            raise TypeError("message.content 형식 오류")
        normalized.append({"role": role, "content": content})
    if require_assistant and not has_assistant:
        raise ValueError("assistant 메시지가 없습니다.")
    return normalized


def _load_split(folder: str, split: str, token: str):
    from datasets import load_dataset
    from huggingface_hub import hf_hub_download
    filename = f"{folder}/{split}-00000-of-00001.parquet"
    local_path = hf_hub_download(repo_id=HF_DATASET_REPO, repo_type="dataset", filename=filename, token=token)
    return load_dataset("parquet", data_files={split: local_path}, split=split)


def _find_training_contract(task_type: str, token: str) -> dict:
    array_key = TASK_ARRAY_KEYS[task_type]
    errors: list[str] = []
    for folder in TASK_SEARCH_FOLDERS[task_type]:
        try:
            dataset = _load_split(folder, "train", token)
        except Exception as exc:
            errors.append(f"{folder}: {exc}")
            continue
        for row_index, row in enumerate(dataset):
            messages = row.get("messages", [])
            system_messages = [m for m in messages if m.get("role") == "system"]
            user_messages = [m for m in messages if m.get("role") == "user"]
            assistant_messages = [m for m in messages if m.get("role") == "assistant"]
            if not system_messages or not user_messages or not assistant_messages:
                continue
            try:
                user_obj = json.loads(message_text(user_messages[0]))
                assistant_obj = json.loads(message_text(assistant_messages[0]))
            except Exception:
                continue
            if user_obj.get("task_type") != task_type or not isinstance(assistant_obj.get(array_key), list):
                continue
            return {"folder": folder, "row_index": row_index, "system_prompt": message_text(system_messages[0]), "user_text": message_text(user_messages[0])}
    raise RuntimeError(f"{task_type} 학습 프롬프트를 찾지 못했습니다. errors={errors}")


def get_training_contracts(token: str) -> dict[str, dict]:
    global _contracts
    if _contracts is None:
        with _contract_lock:
            if _contracts is None:
                _contracts = {task: _find_training_contract(task, token) for task in TASK_ARRAY_KEYS}
    return _contracts


def build_prompt_messages(task_type: str, user_obj: dict, token: str) -> list[dict]:
    contract = get_training_contracts(token)[task_type]
    user_text = json.dumps(user_obj, ensure_ascii=False, indent=2 if "\n" in contract["user_text"] else None)
    return [{"role": "system", "content": contract["system_prompt"]}, {"role": "user", "content": user_text}]


def get_system_prompts(token: str) -> dict[str, str]:
    return {task: contract["system_prompt"] for task, contract in get_training_contracts(token).items()}
