# services/llm_service.py
import logging
import time

from agents.srs_core.parser import extract_json
from agents.srs_pipeline_config import PIPELINE
from services.llm_client import call_llm

logger = logging.getLogger(__name__)


class LLMService:

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        for attempt in range(1, PIPELINE["max_retries"] + 1):
            try:
                return call_llm(system_prompt, user_prompt)
            except RuntimeError as e:
                logger.warning("llm: attempt %d failed — %s", attempt, e)
                if attempt < PIPELINE["max_retries"]:
                    time.sleep(PIPELINE["retry_delay"] * attempt)
        logger.error("llm: all attempts failed")
        return ""

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        for attempt in range(1, PIPELINE["max_retries"] + 1):
            raw = self.complete(system_prompt, user_prompt)

            print(f"\n[LLM RAW {attempt}차]\n{raw[:300]}\n")

            if not raw:
                continue

            result = extract_json(raw)
            if not result.get("_parse_error"):
                return result

            # JSON 아닌 텍스트 나오면 더 강하게 재시도
            user_prompt = f"""{user_prompt}

    반드시 아래 형식의 JSON만 출력하라. 설명 금지.
    {{"topics": ["키워드1", "키워드2"]}}"""

        logger.error("llm: JSON 추출 최종 실패")
        return {"requirements": [], "_parse_error": True}
