import json, re, logging

logger = logging.getLogger(__name__)

def extract_json(raw: str) -> dict:
    if not raw or not raw.strip():
        return _fallback()

    for name, fn in [
        ("direct",     _try_direct),
        ("code_fence", _try_code_fence),
        ("brace_scan", _try_brace_scan),
    ]:
        result = fn(raw)
        if result is not None:
            logger.debug("parser: success via '%s'", name)
            return _normalize(result)

    logger.error("parser: all strategies failed. raw=%.200s", raw)
    return _fallback(raw)

def _try_direct(raw):
    try:    return json.loads(raw.strip())
    except: return None

def _try_code_fence(raw):
    for block in re.findall(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.S):
        try:    return json.loads(block.strip())
        except: continue
    return None

def _try_brace_scan(raw):
    # '{'로 시작해서 '}'로 끝나는 가장 긴 범위를 찾음 (Greedy)
    s = raw.find('{')
    e = raw.rfind('}')
    if s != -1 and e != -1 and s < e:
        # 괄호 사이의 텍스트가 순수 JSON인지 확인
        candidate = raw[s:e+1]
        try:
            return json.loads(candidate)
        except:
            # 괄호 사이에 불필요한 줄바꿈이나 텍스트가 섞여있을 경우 대비 
            # (하지만 보통 여기서 성공합니다)
            return None
    return None

def _normalize(data) -> dict:
    if isinstance(data, dict):  return data
    if isinstance(data, list):  return {"requirements": data}
    return {"requirements": [], "_raw": data}

def _fallback(raw="") -> dict:
    return {"requirements": [], "_parse_error": True, "_raw": raw[:500]}