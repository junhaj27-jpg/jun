from django.contrib import admin

from .models import Document, DocumentApproval, DocumentDetail


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        "sn",
        "project",
        "possession_user",
        "progress_status",
        "document_type",
        "version",
        "created_at",
        "updated_at",
    )
    search_fields = ("project__name", "possession_user__user_id", "document_type__code", "version")


@admin.register(DocumentDetail)
class DocumentDetailAdmin(admin.ModelAdmin):
    list_display = ("sn", "document", "is_deleted", "created_at")
    search_fields = ("document__version", "document__project__name")
    list_filter = ("is_deleted",)


@admin.register(DocumentApproval)
class DocumentApprovalAdmin(admin.ModelAdmin):
    list_display = ("approval_sn", "detail", "approval_status", "created_at", "updated_at")
    search_fields = ("detail__document__version", "approval_status__code")
