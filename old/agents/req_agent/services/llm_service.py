import logging, time
from phase1_config   import call_sllm
from core.parser     import extract_json
from pipeline_config import PIPELINE

logger = logging.getLogger(__name__)

class LLMService:
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        for attempt in range(1, PIPELINE["max_retries"] + 1):
            try:
                return call_sllm(system_prompt, user_prompt)
            except RuntimeError as e:
                logger.warning("llm: attempt %d failed -- %s", attempt, e)
                if attempt < PIPELINE["max_retries"]:
                    time.sleep(PIPELINE["retry_delay"] * attempt)
        logger.error("llm: all attempts failed")
        return ""

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        raw = self.complete(system_prompt, user_prompt)
        if not raw:
            return {"requirements": [], "_llm_error": True}
        result = extract_json(raw)
        if result.get("_parse_error"):
            logger.warning("llm: parse failed. raw=%.200s", raw)
        return result
