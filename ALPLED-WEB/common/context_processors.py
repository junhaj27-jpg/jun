from common.project_selection import resolve_current_project


def _can_manage_projects(user):
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_staff", False):
        return True

    try:
        from common.models import YesNoChoices
        from projects.models import ProjectUserRole

        return ProjectUserRole.objects.filter(
            user=user,
            role_id="ROLE_MANAGER",
            project__is_deleted=YesNoChoices.NO,
        ).exists()
    except Exception:
        return False


def sidebar_projects(request):
    current_project, available_projects = resolve_current_project(request)
    return {
        "current_project": current_project,
        "available_projects": available_projects,
        "can_manage_projects": _can_manage_projects(getattr(request, "user", None)),
    }
