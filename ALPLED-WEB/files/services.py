import mimetypes
from pathlib import Path
from uuid import uuid4

from django.db.models import Q

from common.models import Code
from common.storage import build_s3_uri, delete_object_at_uri, read_bytes_from_uri, save_bytes


FILE_TYPE_SEQUENCE = ("FILE_RFP", "FILE_MEETING")
LEGACY_FILE_TYPE_ALIASES = {
    "RFP": "FILE_RFP",
    "MEETING": "FILE_MEETING",
}

SEARCH_FIELD_CHOICES = (
    ("all", "전체"),
    ("creator", "등록자"),
    ("name", "문서명"),
)


def _get_ordered_codes(code_values):
    code_map = Code.objects.in_bulk(code_values, field_name="code")
    return [code_map[code] for code in code_values if code in code_map]


def get_file_type_choices(*, include_all=True, allowed_codes=None):
    target_codes = allowed_codes or FILE_TYPE_SEQUENCE
    choices = [("all", "전체")] if include_all else []
    for code in _get_ordered_codes(target_codes):
        choices.append((code.code, code.name))
    return tuple(choices)


def apply_file_filters(params, queryset, *, default_file_type="all", allowed_file_types=None):
    file_type = params.get("file_type", default_file_type)
    file_type = LEGACY_FILE_TYPE_ALIASES.get(file_type, file_type)
    search_field = params.get("field", "all")
    query = params.get("q", "").strip()

    if allowed_file_types:
        queryset = queryset.filter(file_type_id__in=allowed_file_types)
        valid_values = {"all", *allowed_file_types}
        if file_type not in valid_values:
            file_type = default_file_type

    if file_type != "all":
        queryset = queryset.filter(file_type_id=file_type)

    if query:
        if search_field == "creator":
            queryset = queryset.filter(created_by__name__icontains=query)
        elif search_field == "name":
            queryset = queryset.filter(name__icontains=query)
        else:
            queryset = queryset.filter(
                Q(created_by__name__icontains=query) | Q(name__icontains=query)
            )

    return queryset, file_type, search_field, query


def build_project_file_rows(queryset, *, start_index=1):
    rows = []
    for index, document in enumerate(queryset, start=start_index):
        rows.append(
            {
                "sn": document.sn,
                "display_no": index,
                "name": document.name,
                "type_name": getattr(document.file_type, "name", "-"),
                "creator_name": getattr(document.created_by, "name", "-") or "-",
                "created_at": document.created_at,
            }
        )
    return rows


def build_project_file_storage_key(project, filename):
    safe_name = Path(filename or "file").name
    return f"project-files/{project.sn}/{uuid4().hex}-{safe_name}"


def guess_file_content_type(filename):
    return mimetypes.guess_type(filename or "")[0] or "application/octet-stream"


def save_project_file_bytes(project, filename, content_bytes):
    storage_key = build_project_file_storage_key(project, filename)
    save_bytes(storage_key, content_bytes, content_type=guess_file_content_type(filename))
    return build_s3_uri(storage_key)


def get_project_file_bytes(project_file):
    return read_bytes_from_uri(project_file.path)


def delete_project_file_bytes(project_file):
    storage_path = str(getattr(project_file, "path", "") or "").strip()
    if not storage_path:
        return
    delete_object_at_uri(storage_path)
