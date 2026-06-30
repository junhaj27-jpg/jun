from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import models

from common.models import CreatedAtMixin, CreatedByMixin, UpdatedAtMixin, UpdatedByMixin, YesNoChoices


class UserManager(BaseUserManager):
    def create_user(self, user_id, password=None, **extra_fields):
        if not user_id:
            raise ValueError("The user_id must be set")

        if "created_by" not in extra_fields and "created_by_id" not in extra_fields:
            admin = self.filter(user_id="admin").only("sn").first()
            if admin is not None:
                extra_fields["created_by"] = admin
            elif extra_fields.get("sn") is not None:
                extra_fields["created_by_id"] = extra_fields["sn"]
        if "updated_by" not in extra_fields and "updated_by_id" not in extra_fields:
            admin = self.filter(user_id="admin").only("sn").first()
            if admin is not None:
                extra_fields["updated_by"] = admin
            elif extra_fields.get("sn") is not None:
                extra_fields["updated_by_id"] = extra_fields["sn"]

        user = self.model(user_id=user_id, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save(using=self._db)
        return user

    def create_superuser(self, user_id, password=None, **extra_fields):
        extra_fields.setdefault("sys_mngr_yn", YesNoChoices.YES)
        extra_fields.setdefault("use_yn", YesNoChoices.YES)
        return self.create_user(user_id, password, **extra_fields)


class User(AbstractBaseUser, CreatedAtMixin, CreatedByMixin, UpdatedAtMixin, UpdatedByMixin):
    last_login = None

    sn = models.AutoField(primary_key=True, db_column="user_sn")
    user_id = models.CharField(max_length=20, unique=True, db_column="user_id")
    password = models.CharField(max_length=256, db_column="user_pswd")
    name = models.CharField(max_length=100, db_column="user_nm")
    department = models.CharField(max_length=100, null=True, blank=True, db_column="dept_nm")
    position = models.CharField(max_length=100, null=True, blank=True, db_column="jbgd_nm")

    sys_mngr_yn = models.CharField(
        max_length=1,
        db_column="sys_mngr_yn",
        choices=YesNoChoices.choices,
        default=YesNoChoices.NO,
    )
    tmpr_pswd_yn = models.CharField(
        max_length=1,
        db_column="tmpr_pswd_yn",
        choices=YesNoChoices.choices,
        default=YesNoChoices.NO,
    )
    use_yn = models.CharField(
        max_length=1,
        db_column="use_yn",
        choices=YesNoChoices.choices,
        default=YesNoChoices.YES,
    )

    objects = UserManager()

    USERNAME_FIELD = "user_id"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        db_table = "tbl_user"
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self) -> str:
        return f"{self.name} ({self.user_id})"

    @property
    def is_active(self):
        return self.use_yn == YesNoChoices.YES

    @is_active.setter
    def is_active(self, value):
        self.use_yn = YesNoChoices.YES if value else YesNoChoices.NO

    @property
    def is_staff(self):
        return self.sys_mngr_yn == YesNoChoices.YES

    def has_perm(self, perm, obj=None):
        return self.is_staff

    def has_module_perms(self, app_label):
        return self.is_staff
