from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from tools.llm.llm_client import LLMClient
from tools.result import ToolResult, error_result, success_result


def send_parallel(
    requests: list[dict[str, Any]],
    *,
    client: LLMClient | None = None,
    max_workers: int = 4,
) -> ToolResult:
    """여러 Chat Completion 요청을 병렬 실행하고 입력 순서대로 반환합니다."""

    if max_workers < 1:
        return error_result("LLM_PARALLEL_INVALID_WORKERS", "max_workers는 1 이상이어야 합니다.")

    llm_client = client or LLMClient()
    results: list[ToolResult | None] = [None] * len(requests)

    def invoke(request: dict[str, Any]) -> ToolResult:
        request_data = dict(request)
        messages = request_data.pop("messages", None)
        if not isinstance(messages, list):
            return error_result(
                "LLM_PARALLEL_INVALID_REQUEST",
                "각 요청에는 messages 목록이 필요합니다.",
                {"request": request},
            )
        return llm_client.chat(messages, **request_data)

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(invoke, request): index
                for index, request in enumerate(requests)
            }
            for future in as_completed(futures):
                results[futures[future]] = future.result()
        return success_result(results)
    except Exception as exc:
        return error_result("LLM_PARALLEL_CALL_FAILED", str(exc))
