from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.cache import patch_cache_control

from common.models import YesNoChoices

from .views import TEMP_PASSWORD_REDIRECT_SESSION_KEY


class TempPasswordChangeRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if self._should_force_password_change(request, user):
            request.session[TEMP_PASSWORD_REDIRECT_SESSION_KEY] = request.get_full_path()
            request.session.modified = True
            messages.warning(request, "최초 비밀번호를 수정해주세요.")
            return redirect("user_profile")

        response = self.get_response(request)
        if getattr(user, "is_authenticated", False):
            patch_cache_control(response, no_cache=True, no_store=True, must_revalidate=True)
        return response

    def _should_force_password_change(self, request, user):
        if not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "tmpr_pswd_yn", None) != YesNoChoices.YES:
            return False

        allowed_paths = {
            reverse("home"),
            reverse("login"),
            reverse("logout"),
            reverse("temp_password_notice"),
            reverse("user_profile"),
        }
        path = request.path_info
        if path in allowed_paths:
            return False
        if path.startswith("/static/"):
            return False
        return True
