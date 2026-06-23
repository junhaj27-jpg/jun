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
    ) -> None:
        self.repository = repository
        self.llm_client = llm_client

    def execute(
        self, docs_sn: int, approval_request_docs_dtl_sn: int
    ) -> dict[str, Any]:
        docs = self.repository.get_docs(docs_sn)
        if docs is None:
            raise LookupError(f"tbl_docs row not found: docs_sn={docs_sn}")
        before_detail = self.repository.get_first_docs_detail(docs_sn)
        if before_detail is None:
            raise LookupError(f"before detail not found: docs_sn={docs_sn}")
        after_detail = self.repository.get_docs_detail(
            docs_sn, approval_request_docs_dtl_sn
        )
        if after_detail is None:
            raise LookupError(
                "approval request detail not found: "
                f"docs_sn={docs_sn}, docs_dtl_sn={approval_request_docs_dtl_sn}"
            )

        before_content = structure_artifact_content(
            str(docs["docs_cd"]),
            load_detail_content(before_detail)["data"],
        )
        after_content = structure_artifact_content(
            str(docs["docs_cd"]),
            load_detail_content(after_detail)["data"],
        )
        raw_changes = group_changes_for_review(
            extract_changes(before_content, after_content)
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
            reference_content = load_detail_content(reference)["data"]
            consistency = check_consistency(
                reference_content, after_content, self.llm_client
            )

        has_issues = bool(changes) or consistency["status"] == "issues_found"
        return {
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
