import json
from typing import Any

from agents.approval_review.prompts import IMPACT_SYSTEM_PROMPT
from config.constants import normalize_docs_cd
from tools.llm.llm_client import LLMClient
from tools.llm.response_parser import parse_json_response


ALLOWED_ARTIFACTS = {"SRS", "UI", "ARCH", "ERD", "DB", "TS"}
MAX_LLM_CHANGES = 10
ARTIFACT_CODE_MAP = {
    "INTERFACE": "UI",
    "ITF": "UI",
}


def classify_impacts(
    changes: list[dict[str, Any]],
    target_docs_cd: str,
    llm_client: LLMClient | None = None,
) -> list[dict[str, Any]]:
    if not changes:
        return []
    excluded_artifact = _artifact_code(target_docs_cd)
    allowed_artifacts = sorted(ALLOWED_ARTIFACTS - {excluded_artifact})
    client = llm_client or LLMClient(timeout=30)
    by_index: dict[int, dict[str, Any]] = {}
    llm_changes = changes[:MAX_LLM_CHANGES]
    if llm_changes:
        payload = [
            {
                "index": offset,
                "change_type": item["change_type"],
                "target_path": item["target_path"],
                "title": item["title"],
                "before": _compact_value(item["before"]),
                "after": _compact_value(item["after"]),
            }
            for offset, item in enumerate(llm_changes)
        ]
        classifications = _request_classifications(
            client,
            payload,
            excluded_artifact,
            allowed_artifacts,
        )
        for classification in classifications:
            if not isinstance(classification, dict):
                continue
            try:
                index = int(classification.get("index"))
            except (TypeError, ValueError):
                continue
            by_index[index] = classification

    results: list[dict[str, Any]] = []
    for index, change in enumerate(changes):
        classification = by_index.get(index)
        if classification is None:
            classification = _fallback_classification(
                index,
                change,
                allowed_artifacts,
            )
        artifacts = [
            _artifact_code(str(value))
            for value in classification.get("affected_artifacts", [])
            if _artifact_code(str(value)) in allowed_artifacts
        ]
        reason = str(classification.get("reason") or "").strip()
        message = str(classification.get("message") or "").strip()
        if not message:
            if artifacts:
                message = (
                    f"{change['title']} 항목이 {_change_label(change['change_type'])}되었습니다. "
                    f"이 변경은 {', '.join(artifacts)} 산출물의 관련 설계와 검증 기준에 "
                    "영향을 줄 수 있으므로, 승인 전에 함께 확인해 주세요."
                )
            else:
                message = (
                    f"{change['title']} 항목이 {_change_label(change['change_type'])}되었습니다. "
                    "현재 확인된 다른 산출물의 직접 영향은 없습니다."
                )
        results.append(
            {
                **change,
                "affected_artifacts": list(dict.fromkeys(artifacts)),
                "reason": reason or "다른 산출물에 미치는 직접적인 영향이 없습니다.",
                "message": message,
                "classification_source": classification.get(
                    "classification_source",
                    "llm",
                ),
            }
        )
    return results


def _request_classifications(
    client: LLMClient,
    payload: list[dict[str, Any]],
    excluded_artifact: str,
    allowed_artifacts: list[str],
) -> list[dict[str, Any]]:
    response = client.chat(
        [
            {"role": "system", "content": IMPACT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "excluded_artifact": excluded_artifact,
                        "allowed_artifacts": allowed_artifacts,
                        "changes": payload,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            },
        ],
        temperature=0,
        max_tokens=1200,
        extra_body={
            "think": False,
            "response_format": {"type": "json_object"},
        },
    )
    if not response["success"]:
        return []
    parsed = parse_json_response(response["data"])
    if not parsed["success"]:
        return []
    value = parsed["data"]
    if isinstance(value, dict) and isinstance(value.get("classifications"), list):
        return value["classifications"]
    if isinstance(value, list):
        return value
    return []


def _fallback_classification(
    index: int,
    change: dict[str, Any],
    allowed_artifacts: list[str],
) -> dict[str, Any]:
    artifacts = _rule_based_artifacts(change)
    artifacts = [item for item in artifacts if item in allowed_artifacts]
    title = str(change.get("title") or change.get("target_path") or "산출물 항목")
    if artifacts:
        reason = (
            f"{title} 변경은 {', '.join(artifacts)} 산출물의 연관 설계 및 검증 기준과 "
            "연결될 가능성이 있습니다."
        )
    else:
        reason = "현재 변경 내용에서 다른 산출물과의 직접적인 연결을 확인하지 못했습니다."
    return {
        "index": index,
        "affected_artifacts": artifacts,
        "reason": reason,
        "classification_source": "rule_fallback",
    }


def _rule_based_artifacts(change: dict[str, Any]) -> list[str]:
    text = " ".join(
        str(change.get(key) or "")
        for key in ("target_path", "title", "before", "after")
    ).lower()
    artifacts: list[str] = []
    rules = {
        "SRS": ("requirement", "요구사항", "기능", "정책"),
        "UI": ("screen", "화면", "버튼", "입력", "메뉴"),
        "ERD": ("entity", "엔티티", "relationship", "관계"),
        "DB": ("table", "column", "테이블", "컬럼", "data_type", "pk", "fk"),
        "ARCH": ("component", "architecture", "컴포넌트", "아키텍처", "배포", "연계"),
        "TS": ("test", "scenario", "시험", "테스트", "검증", "expected"),
    }
    for artifact, keywords in rules.items():
        if any(keyword in text for keyword in keywords):
            artifacts.append(artifact)
    if any(item in artifacts for item in ("SRS", "UI", "ERD", "DB", "ARCH")):
        artifacts.append("TS")
    return list(dict.fromkeys(artifacts))


def _compact_value(value: Any, max_length: int = 500) -> Any:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, default=str)
        return text if len(text) <= max_length else text[:max_length] + "..."
    text = str(value) if value is not None else None
    if text is None or len(text) <= max_length:
        return value
    return text[:max_length] + "..."


def _artifact_code(value: str) -> str:
    normalized = normalize_docs_cd(value)
    return ARTIFACT_CODE_MAP.get(normalized, normalized)


def _change_label(value: str) -> str:
    return {
        "added": "추가",
        "modified": "수정",
        "deleted": "삭제",
    }.get(value, value)
