# 산출물 검증 결과 스키마와 공통 생성 함수를 정의합니다.

from typing import Any, Literal, TypedDict


CheckStatus = Literal["PASS", "FAIL", "WARN"]
Severity = Literal["HIGH", "MEDIUM", "LOW"]


class ValidationCheck(TypedDict):
    check_id: str
    check_name: str
    status: CheckStatus
    severity: Severity
    failure_type: str | None
    message: str
    target_agent: str | None
    target_scope: list[str]


def make_check(
    check_id: str,
    check_name: str,
    passed: bool,
    *,
    failure_type: str,
    message: str,
    target_agent: str,
    target_scope: list[str] | None = None,
    severity: Severity = "HIGH",
    warning: bool = False,
) -> ValidationCheck:
    return {
        "check_id": check_id,
        "check_name": check_name,
        "status": "PASS" if passed else ("WARN" if warning else "FAIL"),
        "severity": severity,
        "failure_type": None if passed else failure_type,
        "message": "검증 통과" if passed else message,
        "target_agent": None if passed else target_agent,
        "target_scope": [] if passed else (target_scope or ["all"]),
    }


def build_validation_result(docs_cd: str, checks: list[ValidationCheck]) -> dict[str, Any]:
    failure_count = sum(check["status"] == "FAIL" for check in checks)
    warning_count = sum(check["status"] == "WARN" for check in checks)
    validation_status = (
        "FAIL" if failure_count else ("PARTIAL_PASS" if warning_count else "PASS")
    )
    return {
        "docs_cd": docs_cd,
        "validation_status": validation_status,
        "failure_count": failure_count,
        "warning_count": warning_count,
        "checks": checks,
    }


def is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def first_list(value: Any, *keys: str) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in keys:
            if isinstance(value.get(key), list):
                return value[key]
    return []


def missing_fields(item: Any, required: list[str]) -> list[str]:
    if not isinstance(item, dict):
        return required
    return [field for field in required if is_empty(item.get(field))]


def missing_keys(item: Any, required: list[str]) -> list[str]:
    if not isinstance(item, dict):
        return required
    return [field for field in required if field not in item]


def duplicate_values(items: list[Any], *keys: str) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        value = next((item.get(key) for key in keys if not is_empty(item.get(key))), None)
        if value is None:
            continue
        normalized = str(value).strip().lower()
        if normalized in seen:
            duplicates.add(str(value))
        seen.add(normalized)
    return sorted(duplicates)
