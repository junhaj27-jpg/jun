from django.conf import settings
from django.db import models

from common.models import (
    CreatedAtMixin,
    CreatedByMixin,
    SoftDeleteMixin,
    UpdatedAtMixin,
    UpdatedByMixin,
    YesNoChoices,
)


class Project(CreatedAtMixin, CreatedByMixin, UpdatedAtMixin, UpdatedByMixin, SoftDeleteMixin):
    sn = models.AutoField(primary_key=True, db_column="prj_sn")
    name = models.CharField(max_length=200, db_column="prj_nm")

    class Meta:
        db_table = "tbl_project"
        verbose_name = "project"
        verbose_name_plural = "projects"

    def __str__(self) -> str:
        return self.name


class ProjectNet(CreatedAtMixin, CreatedByMixin, UpdatedAtMixin, UpdatedByMixin):
    sn = models.AutoField(primary_key=True, db_column="prj_net_sn")
    project = models.ForeignKey(
        Project,
        on_delete=models.PROTECT,
        db_column="prj_sn",
        related_name="nets",
        db_constraint=False,
    )
    name = models.CharField(max_length=100, db_column="prj_net_nm")
    purpose = models.CharField(
        max_length=1000,
        null=True,
        blank=True,
        db_column="prj_net_prps",
    )
    middleware_stack = models.CharField(
        max_length=1000,
        null=True,
        blank=True,
        db_column="mid_stack",
    )
    firewall_settings = models.CharField(
        max_length=1000,
        null=True,
        blank=True,
        db_column="fwl_settings",
    )
    auth_method = models.CharField(
        max_length=1000,
        null=True,
        blank=True,
        db_column="auth_method",
    )
    expected_concurrent_users = models.IntegerField(
        null=True,
        blank=True,
        db_column="expected_smtn",
    )
    cloud_yn = models.CharField(
        max_length=1,
        null=True,
        blank=True,
        db_column="cloud_yn",
        choices=YesNoChoices.choices,
    )
    hardware_spec = models.CharField(
        max_length=1000,
        null=True,
        blank=True,
        db_column="hard_spec",
    )
    remarks = models.CharField(
        max_length=1000,
        null=True,
        blank=True,
        db_column="rmrk",
    )

    class Meta:
        db_table = "tbl_project_net"
        verbose_name = "project network"
        verbose_name_plural = "project networks"

    def __str__(self) -> str:
        return f"{self.project} - {self.name}"


class ProjectUserRole(CreatedAtMixin, CreatedByMixin, UpdatedAtMixin, UpdatedByMixin):
    sn = models.AutoField(primary_key=True, db_column="prj_user_role_sn")
    project = models.ForeignKey(
        Project,
        on_delete=models.PROTECT,
        db_column="prj_sn",
        related_name="user_roles",
        db_constraint=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        db_column="user_sn",
        related_name="project_roles",
        db_constraint=False,
    )
    role = models.ForeignKey(
        "common.Code",
        to_field="code",
        on_delete=models.PROTECT,
        db_column="role_cd",
        related_name="project_roles",
        db_constraint=False,
    )

    class Meta:
        db_table = "tbl_project_user_role"
        verbose_name = "project user role"
        verbose_name_plural = "project user roles"

    def __str__(self) -> str:
        return f"{self.project} / {self.user} / {self.role}"
