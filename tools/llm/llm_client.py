from collections.abc import Callable
from typing import Any

from config.settings import Settings, get_settings
from tools.result import ToolResult, error_result, success_result


LLMTransport = Callable[[str, dict[str, Any], dict[str, str], float], Any]


class LLMClient:
    """OpenAI 호환 Chat Completions API 클라이언트입니다."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model_name: str | None = None,
        timeout: float | None = None,
        *,
        transport: LLMTransport | None = None,
        settings: Settings | None = None,
    ) -> None:
        settings = settings or get_settings()
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.llm_api_key
        self.model_name = model_name or settings.llm_model_name
        self.timeout = timeout or settings.llm_timeout
        self.default_temperature = settings.llm_temperature
        self.default_max_tokens = settings.llm_max_tokens
        self.transport = transport or _requests_transport

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> ToolResult:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": (
                self.default_temperature if temperature is None else temperature
            ),
            "max_tokens": self.default_max_tokens if max_tokens is None else max_tokens,
        }
        if extra_body:
            payload.update(extra_body)

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = self.transport(
                f"{self.base_url}/chat/completions",
                payload,
                headers,
                self.timeout,
            )
            return success_result(response)
        except Exception as exc:
            return error_result(
                "LLM_REQUEST_FAILED",
                str(exc),
                {"base_url": self.base_url, "model_name": self.model_name},
            )


def _requests_transport(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
) -> Any:
    """기본 OpenAI 호환 HTTP transport입니다."""

    import requests

    response = requests.post(url, json=payload, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def send_chat(messages: list[dict[str, Any]], **kwargs: Any) -> ToolResult:
    return LLMClient().chat(messages, **kwargs)
