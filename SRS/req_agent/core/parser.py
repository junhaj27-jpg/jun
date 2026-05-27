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
    for o, c in [('{', '}'), ('[', ']')]:
        s, e = raw.find(o), raw.rfind(c)
        if s != -1 and e != -1 and s < e:
            try:    return json.loads(raw[s:e+1])
            except: continue
    return None

def _normalize(data) -> dict:
    if isinstance(data, dict):  return data
    if isinstance(data, list):  return {"requirements": data}
    return {"requirements": [], "_raw": data}

def _fallback(raw="") -> dict:
    return {"requirements": [], "_parse_error": True, "_raw": raw[:500]}