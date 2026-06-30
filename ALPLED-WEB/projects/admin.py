from django.contrib import admin

from .models import Project, ProjectNet, ProjectUserRole


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("sn", "name", "is_deleted", "created_at", "updated_at")
    search_fields = ("name",)
    list_filter = ("is_deleted",)


@admin.register(ProjectNet)
class ProjectNetAdmin(admin.ModelAdmin):
    list_display = ("sn", "project", "name", "cloud_yn", "created_at", "updated_at")
    search_fields = ("name", "project__name")
    list_filter = ("cloud_yn",)


@admin.register(ProjectUserRole)
class ProjectUserRoleAdmin(admin.ModelAdmin):
    list_display = ("sn", "project", "user", "role", "created_at", "updated_at")
    search_fields = ("project__name", "user__user_id", "role__code")
