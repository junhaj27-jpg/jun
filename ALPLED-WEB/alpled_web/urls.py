"""
URL configuration for alpled_web project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.urls import path, re_path
from django.views.static import serve as static_serve

from common.views import set_current_project_view
from docs.views import (
    approval_approve,
    approval_detail,
    approval_list,
    approval_reject,
    document_auto_apply,
    document_callback,
    document_cancel_approval,
    document_cancel_edit,
    document_confirm,
    document_content,
    document_detail,
    document_editor_config,
    document_generate,
    document_history_preview,
    document_history_list,
    document_job_status,
    document_lock,
    document_request_approval,
    document_restore_revision,
    document_save,
)
from files.views import file_list
from projects.views import project_list
from users.views import (
    download_rfp_template_view,
    home_view,
    login_view,
    logout_view,
    temp_password_notice,
    user_list,
    user_profile,
)

urlpatterns = [
    path("", home_view, name="home"),
    path("downloads/rfp-template/", download_rfp_template_view, name="download_rfp_template"),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("users/profile/", user_profile, name="user_profile"),
    path("users/profile/notice/", temp_password_notice, name="temp_password_notice"),
    path("users/", user_list, name="user_list"),
    path("projects/", project_list, name="project_list"),
    path("files/", file_list, name="file_list"),
    path("docs/generate/", document_generate, name="doc_generate"),
    path("docs/history/", document_history_list, name="doc_history_list"),
    path("docs/jobs/status/", document_job_status, name="doc_job_status"),
    path("docs/documents/<int:document_sn>/", document_detail, name="doc_detail"),
    path("docs/documents/<int:document_sn>/lock/", document_lock, name="doc_lock"),
    path("docs/documents/<int:document_sn>/save/", document_save, name="doc_save"),
    path("docs/documents/<int:document_sn>/cancel-edit/", document_cancel_edit, name="doc_cancel_edit"),
    path("docs/documents/<int:document_sn>/confirm/", document_confirm, name="doc_confirm"),
    path("docs/documents/<int:document_sn>/content/", document_content, name="doc_content"),
    path("docs/documents/<int:document_sn>/editor-config/", document_editor_config, name="doc_editor_config"),
    path("docs/documents/<int:document_sn>/callback/", document_callback, name="doc_callback"),
    path("docs/documents/<int:document_sn>/auto-apply/", document_auto_apply, name="doc_auto_apply"),
    path("docs/documents/<int:document_sn>/request-approval/", document_request_approval, name="doc_request_approval"),
    path("docs/documents/<int:document_sn>/history/<int:detail_sn>/preview/", document_history_preview, name="doc_history_preview"),
    path("docs/documents/<int:document_sn>/history/<int:detail_sn>/restore/", document_restore_revision, name="doc_restore_revision"),
    path("docs/approvals/", approval_list, name="doc_approval_list"),
    path("docs/approvals/<int:approval_sn>/", approval_detail, name="doc_approval_detail"),
    path("docs/approvals/<int:approval_sn>/cancel/", document_cancel_approval, name="doc_cancel_approval"),
    path("docs/approvals/<int:approval_sn>/approve/", approval_approve, name="doc_approval_approve"),
    path("docs/approvals/<int:approval_sn>/reject/", approval_reject, name="doc_approval_reject"),
    path("projects/current/", set_current_project_view, name="set_current_project"),
    path('admin/', admin.site.urls),
]

if getattr(settings, "SERVE_STATIC_LOCALLY", False):
    urlpatterns += [
        re_path(r"^static/(?P<path>.*)$", static_serve, {"document_root": str(settings.BASE_DIR / "static")}),
    ]
