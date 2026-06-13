# 데이터베이스 컬럼명을 표준 명명 규칙으로 변환합니다.

import re


def standardize_name(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z가-힣]+", "_", value).strip("_").lower()
    return normalized or "item"


def table_name(entity_name: str) -> str:
    return f"tbl_{standardize_name(entity_name)}"


def primary_key_name(entity_name: str) -> str:
    return f"{standardize_name(entity_name)}_sn"
