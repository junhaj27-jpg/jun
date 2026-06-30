# ALPLED Core

## 승인요청 정합성 검증

`POST /approval-review`에는 `tbl_docs_approve.docs_aprv_sn`만 전달합니다.
응답으로 받은 `job_id`는 `GET /approval-review-jobs/{job_id}`로 조회합니다.

```json
{
  "docs_aprv_sn": 1
}
```

검증 Worker는 승인요청의 `docs_dtl_sn`을 승인 후 데이터로 사용하고, 같은
`docs_sn`의 직전 상세 데이터를 승인 전 데이터로 선택합니다. 작업 상태, 구조화된
전/후 JSON, 최종 검증 결과와 오류는 `tbl_approval_review_job`에서 조회합니다.
