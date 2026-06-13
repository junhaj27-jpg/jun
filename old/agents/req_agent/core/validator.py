import re, logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_STOPWORDS = {
    "이","그","저","것","수","및","등","를","을","에","의","은","는","가",
    "으로","로","도","만","과","와","하다","있다","되다","이다","위해","대한",
    "the","a","an","is","are","was","to","of","in","for","on","with",
}

@dataclass
class GroundingResult:
    is_grounded:    bool
    score:          float
    matched_tokens: list[str]
    strategy:       str
    reason:         str

def is_grounded(req: dict, minutes: str, rag, *, 
                lex_threshold=0.25, rag_threshold=0.75, min_matches=2) -> GroundingResult:
    text = " ".join(filter(None, [
        req.get("requirement_name", ""),
        req.get("description", ""),
    ]))
    if not text.strip():
        return GroundingResult(False, 0.0, [], "none", "empty text")

    lex = _lexical(text, minutes, lex_threshold, min_matches)

    if lex.score >= lex_threshold * 2 and len(lex.matched_tokens) >= min_matches * 2:
        return GroundingResult(True, lex.score, lex.matched_tokens, "lexical", "high lexical overlap")

    if rag is not None:
        rag_score = _rag(text, rag, rag_threshold)
        combined  = (lex.score + rag_score) / 2
        passed    = rag_score >= rag_threshold or (combined >= lex_threshold and len(lex.matched_tokens) >= min_matches)
        return GroundingResult(passed, combined, lex.matched_tokens, "combined", f"combined={combined:.2f}")

    passed = lex.score >= lex_threshold and len(lex.matched_tokens) >= min_matches
    return GroundingResult(passed, lex.score, lex.matched_tokens, "lexical", lex.reason)

def _tokenize(text):
    tokens = re.findall(r"[가-힣]{2,}|[a-zA-Z]{3,}", text)
    return {t.lower() for t in tokens if t.lower() not in _STOPWORDS}

def _lexical(req_text, minutes, threshold, min_matches):
    req_t = _tokenize(req_text)
    min_t = _tokenize(minutes)
    if not req_t:
        return GroundingResult(False, 0.0, [], "lexical", "no tokens")
    matched = sorted(req_t & min_t)
    score   = len(matched) / len(req_t)
    return GroundingResult(score >= threshold and len(matched) >= min_matches,
                           score, matched, "lexical", f"{len(matched)}/{len(req_t)}")

def _rag(text, rag, threshold):
    try:
        results = rag.query(text, top_k=3)
        return max((r.get("score", 0.0) for r in results), default=0.0)
    except Exception as e:
        logger.warning("rag grounding failed: %s", e)
        return 0.0