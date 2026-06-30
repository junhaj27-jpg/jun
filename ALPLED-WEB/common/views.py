from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from common.project_selection import get_project_switch_next_url, resolve_current_project, set_current_project


@login_required(login_url="home")
def set_current_project_view(request):
    current_project, available_projects = resolve_current_project(request)
    project_sn = request.POST.get("project_sn")

    next_project = current_project
    if project_sn:
        matched_project = next(
            (project for project in available_projects if str(project.sn) == str(project_sn)),
            None,
        )
        if matched_project is not None:
            next_project = matched_project

    set_current_project(request, next_project)
    setattr(request, "_project_selection_cache", (next_project, available_projects))
    return redirect(get_project_switch_next_url(request))
