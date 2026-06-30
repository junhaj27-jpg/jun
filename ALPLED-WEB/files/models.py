from django.db import models

from common.models import CreatedAtMixin, CreatedByMixin, UpdatedAtMixin, UpdatedByMixin


class ProjectFile(CreatedAtMixin, CreatedByMixin, UpdatedAtMixin, UpdatedByMixin):
    sn = models.AutoField(primary_key=True, db_column="file_sn")
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.PROTECT,
        db_column="prj_sn",
        related_name="files",
        db_constraint=False,
    )
    file_type = models.ForeignKey(
        "common.Code",
        to_field="code",
        on_delete=models.PROTECT,
        db_column="file_cd",
        related_name="project_files",
        db_constraint=False,
    )
    name = models.CharField(max_length=100, db_column="file_nm")
    path = models.CharField(max_length=300, db_column="file_path")
    size = models.IntegerField(db_column="file_size")
    extension = models.CharField(max_length=4, db_column="file_ext")

    class Meta:
        db_table = "tbl_file"
        verbose_name = "project file"
        verbose_name_plural = "project files"

    def __str__(self) -> str:
        return self.name
