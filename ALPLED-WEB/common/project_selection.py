import re
from urllib.parse import urlsplit

from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from common.models import YesNoChoices
from projects.models import Project
from users.models import User


CURRENT_PROJECT_SESSION_KEY = "current_project_sn"
PROJECT_ROLE_CODES = ("ROLE_MEMBER", "ROLE_MANAGER")
_REQUEST_CACHE_ATTR = "_project_selection_cache"
_DOCUMENT_DETAIL_PATH_RE = re.compile(r"^/docs/documents/(?P<document_sn>\d+)(?:/|$)")
_APPROVAL_DETAIL_PATH_RE = re.compile(r"^/docs/approvals/(?P<approval_sn>\d+)(?:/|$)")


def get_request_user(request):
    user = getattr(request, "user", None)
    if getattr(user, "is_authenticated", False) and hasattr(user, "sn"):
        return user
    return User.objects.filter(user_id="admin").first() or User.objects.order_by("sn").first()


def get_available_projects_for_user(user):
    if user is None:
        return Project.objects.none()

    if getattr(user, "is_staff", False):
        return Project.objects.filter(is_deleted=YesNoChoices.NO).order_by("name", "sn")

    return (
        Project.objects.filter(
            is_deleted=YesNoChoices.NO,
            user_roles__user=user,
            user_roles__role_id__in=PROJECT_ROLE_CODES,
        )
        .distinct()
        .order_by("name", "sn")
    )


def set_current_project(request, project):
    if project is None:
        request.session.pop(CURRENT_PROJECT_SESSION_KEY, None)
        return
    request.session[CURRENT_PROJECT_SESSION_KEY] = project.sn


def get_safe_next_url(request):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return request.META.get("HTTP_REFERER") or "/"


def get_project_switch_next_url(request):
    next_url = get_safe_next_url(request)
    path = urlsplit(next_url).path

    document_match = _DOCUMENT_DETAIL_PATH_RE.match(path)
    if document_match:
        document_code = ""
        try:
            from docs.models import Document

            document = (
                Document.objects.filter(sn=document_match.group("document_sn"))
                .only("document_type_id")
                .first()
            )
            document_code = getattr(document, "document_type_id", "") or ""
        except Exception:
            document_code = ""
        if document_code:
            return f"{reverse('doc_generate')}?docs_cd={document_code}&resume=1"
        return f"{reverse('doc_history_list')}?docs_cd=all"

    if _APPROVAL_DETAIL_PATH_RE.match(path):
        return reverse("doc_approval_list")

    return next_url


def resolve_current_project(request):
    cached = getattr(request, _REQUEST_CACHE_ATTR, None)
    if cached is not None:
        return cached

    user = get_request_user(request)
    projects = list(get_available_projects_for_user(user))

    selected_project_sn = (
        request.GET.get("project")
        or request.POST.get("project_sn")
        or request.session.get(CURRENT_PROJECT_SESSION_KEY)
    )

    current_project = None
    if selected_project_sn:
        selected_project_sn = str(selected_project_sn)
        current_project = next(
            (project for project in projects if str(project.sn) == selected_project_sn),
            None,
        )

    if current_project is None and projects:
        current_project = projects[0]

    set_current_project(request, current_project)

    cached = (current_project, projects)
    setattr(request, _REQUEST_CACHE_ATTR, cached)
    return cached
