from django.conf import settings
from django.db import models

from common.models import (
    CreatedAtMixin,
    CreatedByMixin,
    SoftDeleteMixin,
    UpdatedAtMixin,
    UpdatedByMixin,
)


class Document(CreatedAtMixin, CreatedByMixin, UpdatedAtMixin, UpdatedByMixin):
    sn = models.AutoField(primary_key=True, db_column="docs_sn")
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.PROTECT,
        db_column="prj_sn",
        related_name="documents",
        db_constraint=False,
    )
    possession_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        db_column="pssn_user_sn",
        related_name="occupied_documents",
        db_constraint=False,
        null=True,
        blank=True,
    )
    document_type = models.ForeignKey(
        "common.Code",
        to_field="code",
        on_delete=models.PROTECT,
        db_column="docs_cd",
        related_name="documents",
        db_constraint=False,
    )
    progress_status = models.ForeignKey(
        "common.Code",
        to_field="code",
        on_delete=models.PROTECT,
        db_column="docs_prgrs_stts_cd",
        related_name="documents_by_progress",
        db_constraint=False,
        default="PRGRS_PENDING",
    )
    version = models.CharField(max_length=20, db_column="docs_ver")
    modification_content = models.CharField(max_length=100, db_column="mdfcn_cn")

    class Meta:
        db_table = "tbl_docs"
        verbose_name = "document"
        verbose_name_plural = "documents"

    def __str__(self) -> str:
        return f"{self.project} - {self.document_type} v{self.version}"


class DocumentDetail(CreatedAtMixin, CreatedByMixin, SoftDeleteMixin):
    sn = models.AutoField(primary_key=True, db_column="docs_dtl_sn")
    document = models.ForeignKey(
        Document,
        on_delete=models.PROTECT,
        db_column="docs_sn",
        related_name="details",
        db_constraint=False,
    )
    detail_content = models.BinaryField(db_column="docs_dtl_cn", null=True, blank=True)
    path = models.CharField(max_length=300, db_column="docs_path")

    class Meta:
        db_table = "tbl_docs_detail"
        verbose_name = "document detail"
        verbose_name_plural = "document details"

    def __str__(self) -> str:
        return f"{self.document} detail {self.sn}"


class DocumentApproval(CreatedAtMixin, CreatedByMixin, UpdatedAtMixin, UpdatedByMixin):
    approval_sn = models.AutoField(primary_key=True, db_column="docs_aprv_sn")
    detail = models.ForeignKey(
        DocumentDetail,
        on_delete=models.PROTECT,
        db_column="docs_dtl_sn",
        related_name="approvals",
        db_constraint=False,
    )
    approval_status = models.ForeignKey(
        "common.Code",
        to_field="code",
        on_delete=models.PROTECT,
        db_column="aprv_stts_cd",
        related_name="document_approvals",
        db_constraint=False,
    )
    request_content = models.CharField(max_length=100, db_column="dmnd_cn")
    rejection_reason = models.CharField(
        max_length=100,
        db_column="rjct_rsn",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "tbl_docs_approve"
        verbose_name = "document approval"
        verbose_name_plural = "document approvals"

    def __str__(self) -> str:
        return f"{self.detail} / {self.approval_status}"

    @property
    def sn(self):
        return self.approval_sn


class GenerationJob(models.Model):
    sn = models.AutoField(primary_key=True, db_column="job_sn")
    job_id = models.CharField(max_length=36, unique=True, db_column="job_id")
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.DO_NOTHING,
        db_column="prj_sn",
        related_name="generation_jobs",
        db_constraint=False,
    )
    document_type = models.ForeignKey(
        "common.Code",
        to_field="code",
        on_delete=models.DO_NOTHING,
        db_column="docs_cd",
        related_name="generation_jobs_by_type",
        db_constraint=False,
    )
    document = models.ForeignKey(
        Document,
        on_delete=models.DO_NOTHING,
        db_column="docs_sn",
        related_name="generation_jobs",
        db_constraint=False,
        null=True,
        blank=True,
    )
    job_status = models.ForeignKey(
        "common.Code",
        to_field="code",
        on_delete=models.DO_NOTHING,
        db_column="job_stts_cd",
        related_name="generation_jobs_by_status",
        db_constraint=False,
        default="PRGRS_PENDING",
    )
    progress_rate = models.IntegerField(db_column="progress_rate", default=0)
    request_payload = models.JSONField(db_column="request_json")
    result_payload = models.JSONField(db_column="result_json", null=True, blank=True)
    error_code = models.CharField(max_length=100, db_column="error_cd", null=True, blank=True)
    error_message = models.TextField(db_column="error_msg", null=True, blank=True)
    retry_count = models.IntegerField(db_column="retry_cnt", default=0)
    max_retry_count = models.IntegerField(db_column="max_retry_cnt", default=1)
    active_key = models.CharField(max_length=200, db_column="active_key", null=True, blank=True)
    request_id = models.CharField(max_length=100, db_column="request_id", null=True, blank=True)
    requested_at = models.DateTimeField(db_column="requested_dt")
    started_at = models.DateTimeField(db_column="started_dt", null=True, blank=True)
    completed_at = models.DateTimeField(db_column="completed_dt", null=True, blank=True)
    heartbeat_at = models.DateTimeField(db_column="heartbeat_dt", null=True, blank=True)
    updated_at = models.DateTimeField(db_column="updated_dt")

    class Meta:
        db_table = "tbl_generation_job"
        managed = False
        verbose_name = "generation job"
        verbose_name_plural = "generation jobs"

    def __str__(self) -> str:
        return f"{self.job_id} / {self.job_status_id}"


class ApprovalReviewJob(models.Model):
    sn = models.BigAutoField(primary_key=True, db_column="job_sn")
    job_id = models.CharField(max_length=36, unique=True, db_column="job_id")
    approval = models.ForeignKey(
        DocumentApproval,
        on_delete=models.DO_NOTHING,
        db_column="docs_aprv_sn",
        related_name="review_jobs",
        db_constraint=False,
    )
    document = models.ForeignKey(
        Document,
        on_delete=models.DO_NOTHING,
        db_column="docs_sn",
        related_name="approval_review_jobs",
        db_constraint=False,
    )
    approval_request_detail = models.ForeignKey(
        DocumentDetail,
        on_delete=models.DO_NOTHING,
        db_column="approval_request_docs_dtl_sn",
        related_name="approval_review_requests",
        db_constraint=False,
    )
    before_detail = models.ForeignKey(
        DocumentDetail,
        on_delete=models.DO_NOTHING,
        db_column="before_docs_dtl_sn",
        related_name="approval_reviews_as_before",
        db_constraint=False,
        null=True,
        blank=True,
    )
    after_detail = models.ForeignKey(
        DocumentDetail,
        on_delete=models.DO_NOTHING,
        db_column="after_docs_dtl_sn",
        related_name="approval_reviews_as_after",
        db_constraint=False,
        null=True,
        blank=True,
    )
    before_data = models.JSONField(db_column="before_data_json", null=True, blank=True)
    after_data = models.JSONField(db_column="after_data_json", null=True, blank=True)
    status_code = models.CharField(max_length=30, db_column="job_stts_cd", default="QUEUED")
    step_code = models.CharField(max_length=50, db_column="job_step_cd", null=True, blank=True)
    progress_rate = models.IntegerField(db_column="progress_rate", default=0)
    message = models.CharField(max_length=500, db_column="message_cn", null=True, blank=True)
    request_data = models.JSONField(db_column="request_json")
    result = models.JSONField(db_column="result_json", null=True, blank=True)
    error_code = models.CharField(max_length=100, db_column="error_cd", null=True, blank=True)
    error_message = models.TextField(db_column="error_msg", null=True, blank=True)
    request_id = models.CharField(max_length=100, db_column="request_id", null=True, blank=True)
    worker_id = models.CharField(max_length=100, db_column="worker_id", null=True, blank=True)
    active_key = models.CharField(max_length=200, db_column="active_key", null=True, blank=True)
    requested_at = models.DateTimeField(db_column="requested_dt")
    started_at = models.DateTimeField(db_column="started_dt", null=True, blank=True)
    completed_at = models.DateTimeField(db_column="completed_dt", null=True, blank=True)
    heartbeat_at = models.DateTimeField(db_column="heartbeat_dt", null=True, blank=True)
    updated_at = models.DateTimeField(db_column="updated_dt")

    class Meta:
        db_table = "tbl_approval_review_job"
        managed = False
        verbose_name = "approval review job"
        verbose_name_plural = "approval review jobs"

    def __str__(self) -> str:
        return f"{self.job_id} / {self.status_code}"
