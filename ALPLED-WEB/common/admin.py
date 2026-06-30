from django.contrib import admin
from .models import Code


@admin.register(Code)
class CodeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "remarks", "created_at", "updated_at")
    search_fields = ("code", "name", "remarks")
