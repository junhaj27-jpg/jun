from collections.abc import Callable
from typing import Any

from agents.approval_review.processors import (
    check_consistency,
    classify_impacts,
    extract_changes,
    group_changes_for_review,
    load_detail_content,
    structure_artifact_content,
)
from agents.approval_review.repository import ApprovalReviewRepository
from tools.llm.llm_client import LLMClient


class ApprovalReviewAgent:
    def __init__(
        self,
        repository: ApprovalReviewRepository,
        llm_client: LLMClient | None = None,
        progress_callback: Callable[[str, int, str], None] | None = None,
        snapshot_callback: Callable[[int, int, Any, Any], None] | None = None,
    ) -> None:
        self.repository = repository
        self.llm_client = llm_client
        self.progress_callback = progress_callback
        self.snapshot_callback = snapshot_callback

    def execute(
        self,
        docs_sn: int,
        approval_request_docs_dtl_sn: int,
        docs_aprv_sn: int | None = None,
    ) -> dict[str, Any]:
        self._progress("LOADING", 10, "검증 대상 산출물을 불러오고 있습니다.")
        docs = self.repository.get_docs(docs_sn)
        if docs is None:
            raise LookupError(f"tbl_docs row not found: docs_sn={docs_sn}")
        if hasattr(self.repository, "get_review_docs_detail_pair"):
            before_detail, after_detail = self.repository.get_review_docs_detail_pair(
                docs_sn,
                approval_request_docs_dtl_sn,
            )
        elif hasattr(self.repository, "get_baseline_docs_detail"):
            before_detail = self.repository.get_baseline_docs_detail(
                docs_sn,
                approval_request_docs_dtl_sn,
            )
            after_detail = self.repository.get_docs_detail(
                docs_sn, approval_request_docs_dtl_sn
            )
        elif hasattr(self.repository, "get_previous_docs_detail"):
            before_detail = self.repository.get_previous_docs_detail(
                docs_sn,
                approval_request_docs_dtl_sn,
            )
            after_detail = self.repository.get_docs_detail(
                docs_sn, approval_request_docs_dtl_sn
            )
        else:
            before_detail = self.repository.get_first_docs_detail(docs_sn)
            after_detail = self.repository.get_docs_detail(
                docs_sn, approval_request_docs_dtl_sn
            )
        if before_detail is None:
            raise LookupError(
                "before detail not found: "
                f"docs_sn={docs_sn}, after_docs_dtl_sn={approval_request_docs_dtl_sn}"
            )
        if after_detail is None:
            raise LookupError(
                "approval request detail not found: "
                f"docs_sn={docs_sn}, docs_dtl_sn={approval_request_docs_dtl_sn}"
            )

        before_content = structure_artifact_content(
            str(docs["docs_cd"]),
            load_detail_content(
                before_detail,
                docs_cd=str(docs["docs_cd"]),
            )["data"],
        )
        after_content = structure_artifact_content(
            str(docs["docs_cd"]),
            load_detail_content(
                after_detail,
                docs_cd=str(docs["docs_cd"]),
            )["data"],
        )
        if self.snapshot_callback is not None:
            self.snapshot_callback(
                int(before_detail["docs_dtl_sn"]),
                int(after_detail["docs_dtl_sn"]),
                before_content,
                after_content,
            )
        self._progress("CHANGE_ANALYSIS", 30, "산출물 변경사항을 분석하고 있습니다.")
        raw_changes = group_changes_for_review(
            extract_changes(before_content, after_content)
        )
        self._progress(
            "IMPACT_ANALYSIS",
            50,
            "변경사항이 다른 산출물에 미치는 영향을 분석하고 있습니다.",
        )
        changes = classify_impacts(
            raw_changes,
            str(docs["docs_cd"]),
            self.llm_client,
        )
        counts = {
            f"{change_type}_count": sum(
                item["change_type"] == change_type for item in changes
            )
            for change_type in ("added", "modified", "deleted")
        }

        reference = self.repository.get_latest_requirement_json(
            int(docs["prj_sn"])
        )
        if reference is None:
            consistency = {
                "status": "skipped",
                "summary": {
                    "matched_count": 0,
                    "missing_count": 0,
                    "added_count": 0,
                    "conflict_count": 0,
                },
                "messages": [
                    {
                        "type": "skipped",
                        "text": "같은 프로젝트의 최신 요구사항 JSON 파일이 없어 정합성 검토를 생략했습니다.",
                    }
                ],
            }
        else:
            self._progress(
                "CONSISTENCY_CHECK",
                75,
                "최신 요구사항과 승인 요청 산출물의 정합성을 검증하고 있습니다.",
            )
            reference_content = load_detail_content(reference)["data"]
            consistency = check_consistency(
                reference_content, after_content, self.llm_client
            )

        has_issues = bool(changes) or consistency["status"] == "issues_found"
        return {
            "docs_aprv_sn": docs_aprv_sn,
            "status": "issues_found" if has_issues else (
                "skipped" if consistency["status"] == "skipped" else "ok"
            ),
            "docs_sn": docs_sn,
            "target_docs_cd": docs["docs_cd"],
            "before_docs_dtl_sn": before_detail["docs_dtl_sn"],
            "after_docs_dtl_sn": after_detail["docs_dtl_sn"],
            "reference_requirement_docs_sn": (
                reference.get("docs_sn") if reference else None
            ),
            "reference_requirement_docs_dtl_sn": (
                reference.get("docs_dtl_sn") if reference else None
            ),
            "reference_requirement_file_sn": (
                reference.get("file_sn") if reference else None
            ),
            "change_review": {"summary": counts, "changes": changes},
            "consistency_check": consistency,
        }

    def _progress(self, step: str, progress: int, message: str) -> None:
        if self.progress_callback is not None:
            self.progress_callback(step, progress, message)
