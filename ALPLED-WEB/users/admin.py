from django.contrib import admin

from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("sn", "user_id", "name", "sys_mngr_yn", "use_yn", "created_at")
    search_fields = ("user_id", "name", "department", "position")
    list_filter = ("sys_mngr_yn", "tmpr_pswd_yn", "use_yn")
