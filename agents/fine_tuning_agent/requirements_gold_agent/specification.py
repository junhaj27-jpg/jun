from __future__ import annotations

from typing import Any

from .utils import dedupe_preserve


def build_gold_specification(final_requirements: list[dict[str, Any]], document: dict[str, Any]) -> list[dict[str, Any]]:
    """최종 GOLD 요구사항을 인수인계·RAG 후속 처리용 명세서 행으로 변환한다.

    이 단계는 SLLM을 다시 호출하지 않는 고정 로직이다. RAG 검증은 후속 모듈에서
    `rag_validation.status`를 업데이트하는 방식으로 붙인다.
    """
    rows: list[dict[str, Any]] = []
    for item in final_requirements:
        gold_id = str(item.get("gold_id", "")).strip()
        sources = dedupe_preserve(item.get("sources", []))
        rows.append({
            "requirement_id": gold_id,
            "requirement_type": "기능",
            "action_type": str(item.get("action_type", "미지정")).strip(),
            "requirement_name": str(item.get("requirement_name", "")).strip(),
            "requirement_detail": str(item.get("requirement_detail", "")).strip(),
            "source": sources,
            "source_text": "; ".join(sources),
            "source_task2_ids": dedupe_preserve(item.get("source_task2_ids", [])),
            "source_atomic_ids": dedupe_preserve(item.get("source_atomic_ids", [])),
            "processing_type": str(item.get("processing_type", "")).strip(),
            "merge_basis": str(item.get("merge_basis", "")).strip(),
            "rag_validation": {"status": "NOT_APPLIED", "evidence": [], "notes": "GOLD 생성 후 RAG 검증 모듈에서 갱신"},
        })
    return rows


def specification_csv_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    csv_rows: list[dict[str, str]] = []
    for row in rows:
        csv_rows.append({
            "requirement_id": str(row.get("requirement_id", "")),
            "requirement_type": str(row.get("requirement_type", "")),
            "action_type": str(row.get("action_type", "")),
            "requirement_name": str(row.get("requirement_name", "")),
            "requirement_detail": str(row.get("requirement_detail", "")),
            "source": "; ".join(row.get("source", []) or []),
            "source_task2_ids": "; ".join(row.get("source_task2_ids", []) or []),
            "source_atomic_ids": "; ".join(row.get("source_atomic_ids", []) or []),
            "processing_type": str(row.get("processing_type", "")),
            "merge_basis": str(row.get("merge_basis", "")),
            "rag_status": str((row.get("rag_validation") or {}).get("status", "")),
        })
    return csv_rows
