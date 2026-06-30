"""요구사항에서 업무 이벤트와 상태 후보를 추출합니다."""

from typing import Any


EVENT_KEYWORDS = (
    "등록",
    "신청",
    "승인",
    "반려",
    "검토",
    "수정",
    "삭제",
    "조회",
    "수집",
    "전처리",
    "청킹",
    "임베딩",
    "색인",
    "배치",
    "스케줄",
    "실행",
    "상태조회",
)

STATUS_RULES = (
    ("신청", "REQUESTED"),
    ("승인", "APPROVED"),
    ("반려", "REJECTED"),
    ("검토", "REVIEWING"),
    ("전처리", "PROCESSING"),
    ("청킹", "PROCESSING"),
    ("임베딩", "PROCESSING"),
    ("색인", "PROCESSING"),
    ("처리상태", "PROCESSING"),
    ("완료", "DONE"),
    ("성공", "DONE"),
    ("실패", "FAILED"),
    ("취소", "CANCELED"),
)


def extract_events(requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for requirement in requirements:
        text = f"{requirement['requirement_name']}\n{requirement['detail']}"
        event_names = [keyword for keyword in EVENT_KEYWORDS if keyword in text]
        statuses = [status for keyword, status in STATUS_RULES if keyword in text]
        if "처리" in text and "PROCESSING" not in statuses:
            statuses.append("PROCESSING")
        events.append(
            {
                "requirement_id": requirement["requirement_id"],
                "business_events": list(dict.fromkeys(event_names)),
                "status_candidates": list(dict.fromkeys(statuses)),
            }
        )
    return events
