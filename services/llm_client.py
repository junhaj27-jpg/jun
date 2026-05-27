import os

import requests
from dotenv import load_dotenv

load_dotenv()

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "qwen3:4b")
LLM_API_KEY = os.getenv("LLM_API_KEY", "EMPTY")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.5"))


def call_llm(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout: int = 600,
) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return call_llm_messages(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )


def call_llm_messages(
    messages: list[dict[str, str]],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout: int = 600,
) -> str:
    url = f"{LLM_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL_NAME,
        "messages": messages,
        "temperature": LLM_TEMPERATURE if temperature is None else temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            "LLM 서버 연결 실패. .env의 LLM_BASE_URL과 서버 실행 상태를 확인하세요."
        )
    except KeyError:
        raise RuntimeError(f"LLM 응답 형식 오류:\n{response.text[:300]}")
