"""요구사항 JSON alias를 ERD 생성용 표준 구조로 정규화합니다."""

from typing import Any


ID_KEYS = ("requirement_id", "req_id", "요구사항고유번호", "source_req_id")
TYPE_KEYS = ("requirement_type", "category", "요구사항분류", "type")
NAME_KEYS = ("requirement_name", "req_name", "title", "요구사항명칭", "name")
DETAIL_KEYS = (
    "detail",
    "description",
    "detail_text",
    "content",
    "definition",
    "세부내용",
    "요구사항상세설명",
)


def normalize_requirements(items: list[Any]) -> list[dict[str, Any]]:
    """문서 파서/문분통 산출물을 내부 표준 requirement 목록으로 변환합니다."""

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        requirement_id = _pick(item, ID_KEYS) or f"REQ-{index + 1:03d}"
        requirement_type = _pick(item, TYPE_KEYS) or "미분류"
        requirement_name = _pick(item, NAME_KEYS) or requirement_id
        detail = _join_detail(item)
        normalized.append(
            {
                "requirement_id": str(requirement_id).strip(),
                "requirement_type": str(requirement_type).strip(),
                "requirement_name": str(requirement_name).strip(),
                "detail": detail,
                "source_page": item.get("source_page") or item.get("page") or item.get("페이지"),
                "raw": item,
            }
        )
    return normalized


def _pick(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, "", []):
            return value
    return None


def _join_detail(item: dict[str, Any]) -> str:
    values = []
    for key in DETAIL_KEYS:
        value = item.get(key)
        if value not in (None, "", []):
            values.append(_to_text(value))
    if not values:
        values.append(_to_text(_pick(item, NAME_KEYS)))
    return "\n".join(dict.fromkeys(value for value in values if value)).strip()


def _to_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(_to_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(f"{key}: {_to_text(val)}" for key, val in value.items())
    return str(value or "").strip()
