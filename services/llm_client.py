import os

import requests
try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv():
        return False

load_dotenv()

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "qwen3:4b")
LLM_API_KEY = os.getenv("LLM_API_KEY", "EMPTY")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.5"))
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "600"))


def call_llm(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout: int = LLM_TIMEOUT,
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
    timeout: int = LLM_TIMEOUT,
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
    except requests.exceptions.Timeout:
        raise RuntimeError(
            f"LLM 응답 시간 초과({timeout}초). 입력이 너무 크거나 모델 응답이 느립니다. "
            "더 큰 모델을 쓰거나 입력 크기를 줄여야 합니다."
        )
    except requests.exceptions.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else "unknown"
        response_text = exc.response.text[:1000] if exc.response is not None else ""
        raise RuntimeError(
            f"LLM HTTP 오류({status_code}). 요청 크기, 모델명, 컨텍스트 길이를 확인하세요.\n"
            f"응답 본문: {response_text}"
        ) from exc
    except KeyError:
        raise RuntimeError(f"LLM 응답 형식 오류:\n{response.text[:300]}")
