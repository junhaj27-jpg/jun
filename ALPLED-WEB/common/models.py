from django.conf import settings
from django.db import models
from django.db.models.functions import Now


class YesNoChoices(models.TextChoices):
    YES = "Y", "Yes"
    NO = "N", "No"


class CreatedAtMixin(models.Model):
    created_at = models.DateTimeField(db_column="crt_dt", db_default=Now(), editable=False)

    class Meta:
        abstract = True


class UpdatedAtMixin(models.Model):
    updated_at = models.DateTimeField(db_column="mdfcn_dt", db_default=Now(), editable=False)

    class Meta:
        abstract = True


class CreatedByMixin(models.Model):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        db_column="creatr_sn",
        related_name="%(app_label)s_%(class)s_created",
    )

    class Meta:
        abstract = True


class UpdatedByMixin(models.Model):
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        db_column="mdfr_sn",
        related_name="%(app_label)s_%(class)s_updated",
    )

    class Meta:
        abstract = True


class SoftDeleteMixin(models.Model):
    is_deleted = models.CharField(
        max_length=1,
        db_column="del_yn",
        choices=YesNoChoices.choices,
        default=YesNoChoices.NO,
    )

    class Meta:
        abstract = True

    @property
    def deleted(self) -> bool:
        return self.is_deleted == YesNoChoices.YES


class Code(CreatedAtMixin, CreatedByMixin, UpdatedAtMixin, UpdatedByMixin):
    code = models.CharField(max_length=100, primary_key=True, db_column="code")
    name = models.CharField(max_length=100, db_column="code_nm")
    remarks = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_column="rmrk_cn",
    )

    class Meta:
        db_table = "tbl_code"
        verbose_name = "code"
        verbose_name_plural = "codes"

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"
