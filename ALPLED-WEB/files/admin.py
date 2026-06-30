from django.contrib import admin

from .models import ProjectFile


@admin.register(ProjectFile)
class ProjectFileAdmin(admin.ModelAdmin):
    list_display = ("sn", "project", "name", "file_type", "size", "created_at", "updated_at")
    search_fields = ("name", "project__name", "file_type__code")
