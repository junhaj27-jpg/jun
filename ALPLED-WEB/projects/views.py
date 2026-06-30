from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from common.pagination import paginate
from common.project_selection import get_safe_next_url

from common.models import Code, YesNoChoices
from common.signals import ensure_initial_reference_data
from users.models import User

from .models import Project, ProjectUserRole


DEFAULT_DOCUMENT_CODE = "DOC_SRS"
PROJECT_MANAGER_ROLE_CODE = "ROLE_MANAGER"
PROJECT_MEMBER_ROLE_CODE = "ROLE_MEMBER"


def _get_admin_user():
    return User.objects.filter(user_id="admin").first()


def _get_default_redirect_url():
    return f"{reverse('doc_history_list')}?docs_cd={DEFAULT_DOCUMENT_CODE}"


def _get_project_redirect_url(request):
    next_url = get_safe_next_url(request)
    if next_url and next_url != "/":
        return next_url
    return reverse("project_list")


def _is_system_admin(user):
    return bool(getattr(user, "is_staff", False))


def _is_assigned_project_manager(user, project=None):
    if not getattr(user, "is_authenticated", False):
        return False

    roles = ProjectUserRole.objects.filter(
        user=user,
        role_id=PROJECT_MANAGER_ROLE_CODE,
        project__is_deleted=YesNoChoices.NO,
    )
    if project is not None:
        roles = roles.filter(project=project)
    return roles.exists()


def _can_access_project_management(user):
    return _is_system_admin(user) or _is_assigned_project_manager(user)


def _can_manage_project_assignments(user):
    return _is_system_admin(user)


def _get_project_queryset_for_user(user):
    projects = Project.objects.filter(is_deleted=YesNoChoices.NO)
    if _is_system_admin(user):
        return projects
    return projects.filter(
        user_roles__user=user,
        user_roles__role_id=PROJECT_MANAGER_ROLE_CODE,
    ).distinct()


def _redirect_no_project_permission(request):
    messages.error(request, "시스템 관리자 또는 프로젝트 관리자로 할당된 사용자만 접근할 수 있습니다.")
    return redirect(_get_default_redirect_url())


def _search_users(request):
    active = request.GET.get("user_active", "all")
    search_field = request.GET.get("user_field", "all")
    query = request.GET.get("user_q", "").strip()

    users = User.objects.all().order_by("sn")
    if active in {"Y", "N"}:
        users = users.filter(use_yn=active)

    if query:
        if search_field == "user_id":
            users = users.filter(user_id__icontains=query)
        elif search_field == "name":
            users = users.filter(name__icontains=query)
        elif search_field == "position":
            users = users.filter(position__icontains=query)
        elif search_field == "department":
            users = users.filter(department__icontains=query)
        else:
            users = users.filter(
                Q(user_id__icontains=query)
                | Q(name__icontains=query)
                | Q(position__icontains=query)
                | Q(department__icontains=query)
            )

    page_obj, pagination_context = paginate(request, users, page_param="user_page")
    return list(page_obj.object_list), active, search_field, query, pagination_context


def _build_project_rows(projects, preserved_querystring=""):
    rows = []
    for project in projects:
        manager_names = list(
            ProjectUserRole.objects.filter(project=project, role_id=PROJECT_MANAGER_ROLE_CODE)
            .select_related("user")
            .order_by("sn")
            .values_list("user__name", flat=True)
        )
        if not manager_names:
            manager_names = list(
                ProjectUserRole.objects.filter(project=project)
                .select_related("user")
                .order_by("sn")
                .values_list("user__name", flat=True)[:1]
            )
        edit_query = urlencode(
            {
                "open_project_form": "1",
                "project_form_mode": "edit",
                "project_sn": project.sn,
            }
        )
        if preserved_querystring:
            edit_query = f"{preserved_querystring}&{edit_query}"

        rows.append(
            {
                "sn": project.sn,
                "project_id": f"PRJ{project.sn:03d}",
                "name": project.name,
                "manager_name": ", ".join(manager_names) if manager_names else "미지정",
                "created_at": project.created_at,
                "is_deleted": project.is_deleted,
                "edit_url": f"{reverse('project_list')}?{edit_query}",
            }
        )
    return rows


@transaction.atomic
def _delete_project(request):
    if not _can_manage_project_assignments(request.user):
        messages.error(request, "프로젝트 삭제는 시스템 관리자만 할 수 있습니다.")
        return False

    project_sn = request.POST.get("project_sn", "").strip()
    target_project = Project.objects.filter(sn=project_sn, is_deleted=YesNoChoices.NO).first()
    if target_project is None:
        messages.error(request, "삭제할 프로젝트를 찾을 수 없습니다.")
        return False

    target_project.is_deleted = YesNoChoices.YES
    target_project.updated_by = request.user
    target_project.save(update_fields=["is_deleted", "updated_by"])
    messages.success(request, "프로젝트가 삭제되었습니다.")
    return True


def _parse_user_ids(raw_value):
    if not raw_value:
        return []
    return [value.strip() for value in raw_value.split(",") if value.strip()]


def _get_project_roles(actor):
    role_manager, _ = Code.objects.get_or_create(
        code=PROJECT_MANAGER_ROLE_CODE,
        defaults={"name": "관리자", "created_by": actor, "updated_by": actor},
    )
    role_member, _ = Code.objects.get_or_create(
        code=PROJECT_MEMBER_ROLE_CODE,
        defaults={"name": "멤버", "created_by": actor, "updated_by": actor},
    )
    return role_manager, role_member


def _build_selected_user_rows(user_ids):
    users_by_id = User.objects.in_bulk(user_ids, field_name="user_id")
    rows = []
    for user_id in user_ids:
        user = users_by_id.get(user_id)
        if user is None:
            continue
        rows.append(
            {
                "user_id": user.user_id,
                "name": user.name,
                "position": user.position or "",
                "department": user.department or "",
            }
        )
    return rows


def _get_project_form_state(request, *, can_manage_assignments=False, project_queryset=None):
    form_mode = request.GET.get("project_form_mode", "create")
    if form_mode not in {"create", "edit"}:
        form_mode = "create"

    project_queryset = project_queryset if project_queryset is not None else _get_project_queryset_for_user(request.user)

    project_sn = request.GET.get("project_sn", "").strip()
    project = project_queryset.filter(sn=project_sn).first() if project_sn else None
    if form_mode == "edit" and project is None:
        form_mode = "create"
        project_sn = ""

    if form_mode == "create" and not can_manage_assignments:
        project = None
        project_sn = ""

    project_name = request.GET.get("project_name", "").strip()
    manager_user_ids = _parse_user_ids(request.GET.get("manager_user_ids", ""))
    member_user_ids = _parse_user_ids(request.GET.get("member_user_ids", ""))

    if form_mode == "edit" and project is not None and not request.GET.get("manager_user_ids") and not request.GET.get("member_user_ids"):
        manager_user_ids = list(
            ProjectUserRole.objects.filter(project=project, role_id=PROJECT_MANAGER_ROLE_CODE)
            .select_related("user")
            .order_by("sn")
            .values_list("user__user_id", flat=True)
        )
        member_user_ids = list(
            ProjectUserRole.objects.filter(project=project, role_id=PROJECT_MEMBER_ROLE_CODE)
            .select_related("user")
            .order_by("sn")
            .values_list("user__user_id", flat=True)
        )
    if form_mode == "edit" and project is not None and not project_name:
        project_name = project.name

    requested_open = request.GET.get("open_project_form") == "1" or request.GET.get("open_project_user_search") == "1"
    open_project_form = requested_open
    if not can_manage_assignments and form_mode != "edit":
        open_project_form = False

    readonly_assignments = not can_manage_assignments

    return {
        "open_project_form": open_project_form,
        "project_form_mode": form_mode,
        "project_form_project_sn": str(project.sn) if project is not None else project_sn,
        "project_form_project_id": f"PRJ{project.sn:03d}" if project is not None else "",
        "project_form_created_at": project.created_at if project is not None else None,
        "project_form_name": project_name,
        "project_form_manager_user_ids": ",".join(manager_user_ids),
        "project_form_member_user_ids": ",".join(member_user_ids),
        "project_form_manager_users": _build_selected_user_rows(manager_user_ids),
        "project_form_member_users": _build_selected_user_rows(member_user_ids),
        "project_form_title": "프로젝트 상세 / 수정" if form_mode == "edit" else "프로젝트 등록",
        "project_form_subtitle": "프로젝트명과 담당 인원을 관리합니다." if can_manage_assignments else "프로젝트 관리자로 할당된 사용자는 프로젝트명만 수정할 수 있습니다.",
        "project_form_submit_label": "수정" if form_mode == "edit" else "프로젝트 등록",
        "project_form_readonly_assignments": readonly_assignments,
        "project_form_can_assign_users": can_manage_assignments,
        "project_form_can_delete": can_manage_assignments and form_mode == "edit",
        "project_form_can_create": can_manage_assignments,
    }


@transaction.atomic
def _save_project(request, *, project=None, can_manage_assignments=False):
    actor = request.user
    project_name = request.POST.get("project_name", "").strip()

    if not project_name:
        messages.error(request, "프로젝트명을 입력해 주세요.")
        return False

    if project is None and not can_manage_assignments:
        messages.error(request, "프로젝트 등록은 시스템 관리자만 할 수 있습니다.")
        return False

    if project is not None and not can_manage_assignments:
        if not _is_assigned_project_manager(actor, project):
            messages.error(request, "프로젝트 관리자로 할당된 프로젝트만 수정할 수 있습니다.")
            return False
        project.name = project_name
        project.updated_by = actor
        project.save(update_fields=["name", "updated_by"])
        messages.success(request, "프로젝트명이 수정되었습니다.")
        return True

    manager_user_ids = list(dict.fromkeys(_parse_user_ids(request.POST.get("manager_user_ids", ""))))
    member_user_ids = list(dict.fromkeys(_parse_user_ids(request.POST.get("member_user_ids", ""))))

    selected_user_ids = list(dict.fromkeys(manager_user_ids + member_user_ids))
    if not selected_user_ids:
        messages.error(request, "최소 1명의 사용자를 추가해야 합니다.")
        return False

    duplicated_user_ids = sorted(set(manager_user_ids).intersection(member_user_ids))
    if duplicated_user_ids:
        messages.error(request, "이미 추가된 사용자가 포함되어 있습니다.")
        return False

    users_by_id = User.objects.in_bulk(selected_user_ids, field_name="user_id")
    missing_user_ids = [user_id for user_id in selected_user_ids if user_id not in users_by_id]
    if missing_user_ids:
        messages.error(request, "선택한 사용자 정보가 존재하지 않습니다.")
        return False

    is_update = project is not None

    try:
        role_manager, role_member = _get_project_roles(actor)

        if project is None:
            project = Project.objects.create(
                name=project_name,
                is_deleted=YesNoChoices.NO,
                created_by=actor,
                updated_by=actor,
            )
        else:
            project.name = project_name
            project.updated_by = actor
            project.save(update_fields=["name", "updated_by"])
            ProjectUserRole.objects.filter(project=project).delete()

        for user_id in manager_user_ids:
            ProjectUserRole.objects.create(
                project=project,
                user=users_by_id[user_id],
                role=role_manager,
                created_by=actor,
                updated_by=actor,
            )

        for user_id in member_user_ids:
            ProjectUserRole.objects.create(
                project=project,
                user=users_by_id[user_id],
                role=role_member,
                created_by=actor,
                updated_by=actor,
            )
    except Exception:
        messages.error(request, "프로젝트를 저장할 수 없습니다.")
        return False

    messages.success(request, "프로젝트가 수정되었습니다." if is_update else "프로젝트가 등록되었습니다.")
    return True


@login_required(login_url="home")
def project_list(request):
    ensure_initial_reference_data()

    if not _can_access_project_management(request.user):
        return _redirect_no_project_permission(request)

    can_manage_assignments = _can_manage_project_assignments(request.user)
    base_projects = _get_project_queryset_for_user(request.user)

    if request.method == "POST":
        action = request.POST.get("action", "create_project")
        if action == "delete_project":
            _delete_project(request)
            return redirect(_get_project_redirect_url(request))

        if action == "create_project" and not can_manage_assignments:
            messages.error(request, "프로젝트 등록은 시스템 관리자만 할 수 있습니다.")
            return redirect(_get_project_redirect_url(request))

        target_project = None
        if action == "update_project":
            project_sn = request.POST.get("project_sn", "").strip()
            target_project = base_projects.filter(sn=project_sn, is_deleted=YesNoChoices.NO).first()
            if target_project is None:
                messages.error(request, "수정할 프로젝트를 찾을 수 없습니다.")
                return redirect(_get_project_redirect_url(request))
        if _save_project(request, project=target_project, can_manage_assignments=can_manage_assignments):
            return redirect(_get_project_redirect_url(request))
        return redirect(_get_project_redirect_url(request))

    query = request.GET.get("q", "").strip()
    search_field = request.GET.get("field", "all")
    preserved_querystring = urlencode(
        {
            "field": search_field,
            "q": query,
        }
    )

    projects = base_projects.order_by("sn")
    if query:
        if search_field == "name":
            projects = projects.filter(name__icontains=query)
        elif search_field == "manager":
            projects = projects.filter(user_roles__user__name__icontains=query).distinct()
        else:
            projects = projects.filter(
                Q(name__icontains=query) | Q(user_roles__user__name__icontains=query)
            ).distinct()

    projects_page, pagination_context = paginate(request, projects)
    project_rows = _build_project_rows(projects_page.object_list, preserved_querystring)
    if can_manage_assignments:
        search_users, user_active, user_search_field, user_query, user_pagination_context = _search_users(request)
        open_project_user_search = request.GET.get("open_project_user_search") == "1"
    else:
        search_users, user_active, user_search_field, user_query = [], "all", "all", ""
        user_pagination_context = {}
        open_project_user_search = False
    project_target_role = request.GET.get("project_target_role", "manager")
    project_form_state = _get_project_form_state(
        request,
        can_manage_assignments=can_manage_assignments,
        project_queryset=base_projects,
    )

    context = {
        "active_menu": "projects",
        "projects": project_rows,
        **pagination_context,
        "search_field": search_field,
        "query": query,
        "preserved_querystring": preserved_querystring,
        "status_filter": request.GET.get("detail_status", "all"),
        "title": "프로젝트 관리",
        "yes_no_choices": YesNoChoices.choices,
        "search_users": search_users,
        "user_search_page_obj": user_pagination_context.get("page_obj"),
        "user_search_page_param": user_pagination_context.get("page_param"),
        "user_search_page_querystring": user_pagination_context.get("page_querystring"),
        "user_search_page_range": user_pagination_context.get("page_range"),
        "user_search_page_ellipsis": user_pagination_context.get("page_ellipsis"),
        "user_active": user_active,
        "user_search_field": user_search_field,
        "user_query": user_query,
        "open_project_user_search": open_project_user_search,
        "project_target_role": project_target_role,
        "admin_user": _get_admin_user(),
        "can_manage_project_assignments": can_manage_assignments,
        "can_create_projects": can_manage_assignments,
        **project_form_state,
    }
    return render(request, "projects/project_list.html", context)
