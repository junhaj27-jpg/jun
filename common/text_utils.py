import re
from typing import Any


STOPWORDS = {
    "요구사항", "시스템", "기능", "제공", "한다", "하여야", "사용", "관리", "지원",
    "대한", "회의록", "관련", "추가", "변경", "검토", "필요",
}


def extract_keywords(text: str, limit: int = 20) -> list[str]:
    result = []
    for token in re.findall(r"[가-힣A-Za-z0-9]{2,}", text or ""):
        if token in STOPWORDS or token.lower() in STOPWORDS:
            continue
        if token not in result:
            result.append(token)
        if len(result) >= limit:
            break
    return result


def join_list(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value if item)
    return str(value or "")
