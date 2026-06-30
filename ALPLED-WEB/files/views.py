import io
import os
import zipfile
from urllib.parse import quote

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from common.pagination import paginate
from common.project_selection import resolve_current_project
from common.signals import ensure_initial_reference_data
from users.models import User

from .models import ProjectFile
from .services import (
    FILE_TYPE_SEQUENCE,
    SEARCH_FIELD_CHOICES,
    apply_file_filters,
    build_project_file_rows,
    delete_project_file_bytes,
    get_file_type_choices,
    get_project_file_bytes,
    guess_file_content_type,
    save_project_file_bytes,
)


MAX_UPLOAD_FILES = 5
MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {"docx", "pdf"}
FILE_TYPE_MAP = {
    "rfp_files": "FILE_RFP",
    "meeting_files": "FILE_MEETING",
}
def _get_actor():
    return User.objects.filter(user_id="admin").first() or User.objects.order_by("sn").first()


def _build_file_list_redirect_url():
    return reverse("file_list")


def _validate_uploaded_files(files):
    if len(files) > MAX_UPLOAD_FILES:
        return f"한 번에 최대 {MAX_UPLOAD_FILES}개 파일까지만 등록할 수 있습니다."

    for uploaded_file in files:
        extension = os.path.splitext(uploaded_file.name)[1].lower().lstrip(".")
        if extension not in ALLOWED_EXTENSIONS:
            return "업로드 가능한 파일 형식은 .docx, .pdf 입니다."
        if uploaded_file.size > MAX_FILE_SIZE:
            return f"각 파일은 최대 {MAX_FILE_SIZE // (1024 * 1024)}MB까지 업로드할 수 있습니다."

    return None


@transaction.atomic
def _upload_files(request, project):
    if project is None:
        messages.error(request, "먼저 프로젝트를 선택해 주세요.")
        return redirect(_build_file_list_redirect_url())

    actor = _get_actor()
    rfp_files = request.FILES.getlist("rfp_files")
    meeting_files = request.FILES.getlist("meeting_files")
    uploaded_files = [*rfp_files, *meeting_files]

    if not uploaded_files:
        messages.error(request, "업로드할 파일을 선택해 주세요.")
        return redirect(_build_file_list_redirect_url())

    validation_error = _validate_uploaded_files(uploaded_files)
    if validation_error:
        messages.error(request, validation_error)
        return redirect(_build_file_list_redirect_url())

    for field_name, files in (("rfp_files", rfp_files), ("meeting_files", meeting_files)):
        for uploaded_file in files:
            extension = os.path.splitext(uploaded_file.name)[1].lower().lstrip(".")
            content_bytes = uploaded_file.read()
            storage_path = save_project_file_bytes(project, uploaded_file.name, content_bytes)
            ProjectFile.objects.create(
                project=project,
                file_type_id=FILE_TYPE_MAP[field_name],
                name=os.path.basename(uploaded_file.name),
                path=storage_path,
                size=uploaded_file.size,
                extension=extension[:4],
                created_by=actor,
                updated_by=actor,
            )

    messages.success(request, "파일을 등록했습니다.")
    return redirect(_build_file_list_redirect_url())


@transaction.atomic
def _delete_files(request, project):
    selected_ids = request.POST.getlist("selected_files")
    if not selected_ids:
        messages.error(request, "파일을 하나 이상 선택해 주세요.")
        return redirect(_build_file_list_redirect_url())

    files = list(ProjectFile.objects.filter(project=project, sn__in=selected_ids))
    try:
        for project_file in files:
            delete_project_file_bytes(project_file)
    except ValueError:
        messages.error(request, "S3 경로가 없는 기존 파일은 삭제 전에 정리해 주세요.")
        return redirect(_build_file_list_redirect_url())

    deleted_count, _ = ProjectFile.objects.filter(project=project, sn__in=selected_ids).delete()
    if deleted_count:
        messages.success(request, "선택한 파일을 삭제했습니다.")
    else:
        messages.error(request, "삭제할 파일이 없습니다.")

    return redirect(_build_file_list_redirect_url())


def _download_files(request, project):
    selected_ids = request.POST.getlist("selected_files")
    if not selected_ids:
        messages.error(request, "파일을 하나 이상 선택해 주세요.")
        return redirect(_build_file_list_redirect_url())

    files = list(ProjectFile.objects.filter(project=project, sn__in=selected_ids).order_by("sn"))
    if not files:
        messages.error(request, "다운로드할 파일이 없습니다.")
        return redirect(_build_file_list_redirect_url())

    if len(files) == 1:
        project_file = files[0]
        try:
            file_bytes = get_project_file_bytes(project_file)
        except ValueError:
            messages.error(request, "S3 경로가 없는 기존 파일은 다운로드할 수 없습니다.")
            return redirect(_build_file_list_redirect_url())
        response = HttpResponse(file_bytes, content_type=guess_file_content_type(project_file.name))
        response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(project_file.name)}"
        return response

    buffer = io.BytesIO()
    try:
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for project_file in files:
                archive.writestr(project_file.name, get_project_file_bytes(project_file))
    except ValueError:
        messages.error(request, "S3 경로가 없는 기존 파일은 다운로드할 수 없습니다.")
        return redirect(_build_file_list_redirect_url())
    buffer.seek(0)

    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = "attachment; filename=project-files.zip"
    return response


@login_required(login_url="home")
def file_list(request):
    ensure_initial_reference_data()
    current_project, _ = resolve_current_project(request)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "upload":
            return _upload_files(request, current_project)
        if action == "delete":
            return _delete_files(request, current_project)
        if action == "download":
            return _download_files(request, current_project)
        return redirect(_build_file_list_redirect_url())

    documents = ProjectFile.objects.none()
    if current_project is not None:
        documents = (
            ProjectFile.objects.filter(
                project=current_project,
                file_type_id__in=FILE_TYPE_SEQUENCE,
            )
            .select_related("file_type", "created_by")
            .order_by("-created_at", "-sn")
        )

    documents, file_type, search_field, query = apply_file_filters(
        request.GET,
        documents,
        allowed_file_types=FILE_TYPE_SEQUENCE,
    )

    documents_page, pagination_context = paginate(request, documents)

    context = {
        "active_menu": "files",
        "title": "파일 관리",
        "current_project": current_project,
        "documents": build_project_file_rows(documents_page.object_list, start_index=documents_page.start_index()),
        **pagination_context,
        "file_type": file_type,
        "search_field": search_field,
        "query": query,
        "file_type_choices": get_file_type_choices(allowed_codes=FILE_TYPE_SEQUENCE),
        "search_field_choices": SEARCH_FIELD_CHOICES,
        "max_upload_files": MAX_UPLOAD_FILES,
        "max_file_size_mb": MAX_FILE_SIZE // (1024 * 1024),
    }
    return render(request, "files/file_list.html", context)
