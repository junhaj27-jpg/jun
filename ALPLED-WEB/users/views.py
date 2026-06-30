import json
import re
from urllib.parse import urlsplit

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.db.models.deletion import ProtectedError
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from common.models import YesNoChoices
from common.pagination import paginate
from common.project_selection import get_safe_next_url
from common.signals import ensure_initial_reference_data
from common.storage import read_bytes_from_uri
from projects.models import ProjectUserRole

from .models import User


DEFAULT_DOCUMENT_CODE = "DOC_SRS"
RFP_TEMPLATE_URI = "s3://alpled-s3/system_docs/rfp_template.docx"
RFP_TEMPLATE_FILENAME = "rfp_template.docx"
TEMP_PASSWORD = "abc1234"
TEMP_PASSWORD_REDIRECT_SESSION_KEY = "temp_password_redirect_url"
USER_ID_PATTERN = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9_]{7,10}$")
USER_TEXT_PATTERN = re.compile(r"^[A-Za-z0-9가-힣_ ]+$")
USER_TEXT_MIN_LENGTH = 2
USER_TEXT_MAX_LENGTH = 100


def _get_authenticated_home_url(user):
    return reverse("home")


def _is_login_destination(url):
    if not url:
        return True
    path = urlsplit(url).path or "/"
    return path in {"/", reverse("home"), reverse("login")}


def _redirect_non_admin(request):
    messages.error(request, "관리자만 접근할 수 있습니다.")
    return redirect(_get_authenticated_home_url(request.user))


def _require_admin(request):
    if getattr(request.user, "is_staff", False):
        return None
    return _redirect_non_admin(request)


@never_cache
def home_view(request):
    ensure_initial_reference_data()

    if request.method == "POST" or not request.user.is_authenticated:
        return login_view(request)

    return render(
        request,
        "home.html",
        {
            "title": "메인",
            "active_menu": "",
            "selected_document_code": "",
        },
    )


@login_required(login_url="home")
def download_rfp_template_view(request):
    try:
        template_bytes = read_bytes_from_uri(RFP_TEMPLATE_URI)
    except Exception:
        messages.error(request, "\ubb38\uc11c \uc591\uc2dd\uc744 \ub2e4\uc6b4\ub85c\ub4dc\ud560 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4.")
        return redirect("home")

    response = HttpResponse(
        template_bytes,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response["Content-Disposition"] = f'attachment; filename="{RFP_TEMPLATE_FILENAME}"'
    return response


@never_cache
def login_view(request):
    ensure_initial_reference_data()

    if request.method == "GET" and request.user.is_authenticated:
        logout(request)

    if request.method == "POST":
        user_id = request.POST.get("user_id", "").strip()
        password = request.POST.get("password", "")

        if not user_id or not password:
            messages.error(request, "아이디와 비밀번호를 입력해 주세요.")
        else:
            user = authenticate(request, user_id=user_id, password=password)
            if user is not None and user.is_active:
                login(request, user)
                next_url = get_safe_next_url(request)
                if _is_login_destination(next_url):
                    next_url = _get_authenticated_home_url(user)
                if user.tmpr_pswd_yn == YesNoChoices.YES:
                    request.session[TEMP_PASSWORD_REDIRECT_SESSION_KEY] = next_url
                    request.session.modified = True
                    return redirect("temp_password_notice")
                return redirect(next_url)
            messages.error(request, "아이디 또는 비밀번호가 올바르지 않습니다.")

    return render(
        request,
        "users/login.html",
        {
            "title": "로그인",
            "next_url": request.POST.get("next") or request.GET.get("next") or "",
        },
    )


@require_POST
@never_cache
def logout_view(request):
    logout(request)
    return redirect("home")


def _demo_users():
    return [
        {
            "sn": index,
            "user_id": f"USER{index:03d}",
            "name": f"사용자 {index:03d}",
            "department": "개발부서" if index != 3 else "부서1",
            "position": "사원" if index % 2 else "대리",
            "use_yn": "N" if index == 3 else "Y",
            "tmpr_pswd_yn": "N",
        }
        for index in range(1, 11)
    ]
def _get_actor():
    return User.objects.filter(user_id="admin").first() or User.objects.order_by("sn").first()


def _build_create_form_data(request=None):
    source = request.POST if request is not None else {}
    return {
        "user_id": source.get("user_id", "").strip(),
        "name": source.get("name", "").strip(),
        "department": source.get("department", "").strip(),
        "position": source.get("position", "").strip(),
        "use_yn": source.get("use_yn", YesNoChoices.YES),
    }


def _validate_required_user_text(value, field_subject):
    length = len(value)
    if (
        length < USER_TEXT_MIN_LENGTH
        or length > USER_TEXT_MAX_LENGTH
        or not USER_TEXT_PATTERN.fullmatch(value)
    ):
        return f"{field_subject} 한글, 영문, 숫자, 밑줄(_)로 최소 2자에서 최대 100자까지 입력할 수 있습니다."
    return ""


def _validate_optional_user_text(value, field_subject):
    if not value:
        return ""
    if len(value) > USER_TEXT_MAX_LENGTH or not USER_TEXT_PATTERN.fullmatch(value):
        return f"{field_subject} 한글, 영문, 숫자, 밑줄(_)로 최대 100자까지 입력할 수 있습니다."
    return ""


def _build_profile_form_data(user, request=None):
    source = request.POST if request is not None else {}
    return {
        "user_id": user.user_id,
        "tmpr_pswd_yn": user.tmpr_pswd_yn,
        "name": source.get("name", user.name).strip(),
        "department": source.get("department", user.department or "").strip(),
        "position": source.get("position", user.position or "").strip(),
        "new_password": source.get("new_password", ""),
        "new_password_confirm": source.get("new_password_confirm", ""),
    }


def _pop_temp_password_redirect_url(request):
    next_url = request.session.pop(TEMP_PASSWORD_REDIRECT_SESSION_KEY, "")
    if next_url:
        request.session.modified = True
    return next_url or _get_authenticated_home_url(request.user)


def _update_profile(request, user):
    form_data = _build_profile_form_data(user, request)

    if not form_data["name"]:
        messages.error(request, "이름을 입력해 주세요.")
        return False, form_data

    error_message = _validate_required_user_text(form_data["name"], "이름은")
    if error_message:
        messages.error(request, error_message)
        return False, form_data

    for field_name, field_label in (("department", "부서는"), ("position", "직급은")):
        error_message = _validate_optional_user_text(form_data[field_name], field_label)
        if error_message:
            messages.error(request, error_message)
            return False, form_data

    password_change_requested = bool(form_data["new_password"] or form_data["new_password_confirm"])
    force_password_change = user.tmpr_pswd_yn == YesNoChoices.YES
    if force_password_change and not password_change_requested:
        messages.error(request, "임시 비밀번호 사용자에게는 새 비밀번호 입력이 필요합니다.")
        return False, form_data

    if password_change_requested:
        if not form_data["new_password"]:
            messages.error(request, "새 비밀번호를 입력해 주세요.")
            return False, form_data
        if form_data["new_password"] != form_data["new_password_confirm"]:
            messages.error(request, "새 비밀번호와 비밀번호 확인이 일치하지 않습니다.")
            return False, form_data
        if force_password_change and form_data["new_password"] == TEMP_PASSWORD:
            messages.error(request, "임시 비밀번호와 동일한 비밀번호로 변경할 수 없습니다.")
            return False, form_data

    user.name = form_data["name"]
    user.department = form_data["department"] or None
    user.position = form_data["position"] or None
    user.updated_by = user

    password_updated = False
    if password_change_requested:
        user.set_password(form_data["new_password"])
        user.tmpr_pswd_yn = YesNoChoices.NO
        password_updated = True

    user.save()
    if password_updated:
        update_session_auth_hash(request, user)
        messages.success(request, "개인 정보와 비밀번호를 변경했습니다.")
    else:
        messages.success(request, "개인 정보를 수정했습니다.")
    return True, _build_profile_form_data(user)


@transaction.atomic
def _create_user(request):
    form_data = _build_create_form_data(request)

    if not form_data["user_id"]:
        messages.error(request, "사원번호를 입력해 주세요.")
        return False, form_data

    if not form_data["name"]:
        messages.error(request, "이름을 입력해 주세요.")
        return False, form_data

    error_message = _validate_required_user_text(form_data["name"], "이름은")
    if error_message:
        messages.error(request, error_message)
        return False, form_data

    for field_name, field_label in (("department", "부서는"), ("position", "직급은")):
        error_message = _validate_optional_user_text(form_data[field_name], field_label)
        if error_message:
            messages.error(request, error_message)
            return False, form_data

    if not USER_ID_PATTERN.fullmatch(form_data["user_id"]):
        messages.error(request, "사원번호는 영문자, 숫자, 밑줄(_) 조합으로 최소 7자에서 최대 10자까지 입력할 수 있습니다.")
        return False, form_data

    if form_data["use_yn"] not in {YesNoChoices.YES, YesNoChoices.NO}:
        messages.error(request, "활성 여부 값이 올바르지 않습니다.")
        return False, form_data

    if User.objects.filter(user_id=form_data["user_id"]).exists():
        messages.error(request, "이미 존재하는 사원번호입니다.")
        return False, form_data

    actor = _get_actor()
    User.objects.create_user(
        user_id=form_data["user_id"],
        password=TEMP_PASSWORD,
        name=form_data["name"],
        department=form_data["department"] or None,
        position=form_data["position"] or None,
        sys_mngr_yn=YesNoChoices.NO,
        tmpr_pswd_yn=YesNoChoices.YES,
        use_yn=form_data["use_yn"],
        created_by=actor,
        updated_by=actor,
    )
    messages.success(request, "사용자를 추가했습니다.")
    return True, _build_create_form_data()


@transaction.atomic
def _reset_user_password(request):
    raw_user_sn = request.POST.get("user_sn", "").strip()
    if not raw_user_sn.isdigit():
        messages.error(request, "초기화할 사용자를 찾을 수 없습니다.")
        return

    target_user = User.objects.filter(sn=int(raw_user_sn)).first()
    if target_user is None:
        messages.error(request, "초기화할 사용자를 찾을 수 없습니다.")
        return

    target_user.set_password(TEMP_PASSWORD)
    target_user.tmpr_pswd_yn = YesNoChoices.YES
    target_user.updated_by = request.user
    target_user.save(update_fields=["password", "tmpr_pswd_yn", "updated_by"])

    if target_user.sn == request.user.sn:
        update_session_auth_hash(request, target_user)

    messages.success(request, f"{target_user.name} 계정의 임시 비밀번호를 초기화했습니다.")


def _get_target_user_from_post(request, error_action):
    raw_user_sn = request.POST.get("user_sn", "").strip()
    if not raw_user_sn.isdigit():
        messages.error(request, f"{error_action}할 사용자를 찾을 수 없습니다.")
        return None

    target_user = User.objects.filter(sn=int(raw_user_sn)).first()
    if target_user is None:
        messages.error(request, f"{error_action}할 사용자를 찾을 수 없습니다.")
        return None
    return target_user


@transaction.atomic
def _update_user(request):
    target_user = _get_target_user_from_post(request, "수정")
    if target_user is None:
        return

    form_data = {
        "name": request.POST.get("name", "").strip(),
        "department": request.POST.get("department", "").strip(),
        "position": request.POST.get("position", "").strip(),
        "use_yn": request.POST.get("use_yn", YesNoChoices.YES),
    }

    if not form_data["name"]:
        messages.error(request, "이름을 입력해 주세요.")
        return
    error_message = _validate_required_user_text(form_data["name"], "이름은")
    if error_message:
        messages.error(request, error_message)
        return

    for field_name, field_label in (("department", "부서는"), ("position", "직급은")):
        error_message = _validate_optional_user_text(form_data[field_name], field_label)
        if error_message:
            messages.error(request, error_message)
            return

    if form_data["use_yn"] not in {YesNoChoices.YES, YesNoChoices.NO}:
        messages.error(request, "활성 여부 값이 올바르지 않습니다.")
        return

    target_user.name = form_data["name"]
    target_user.department = form_data["department"] or None
    target_user.position = form_data["position"] or None
    target_user.use_yn = form_data["use_yn"]
    target_user.updated_by = request.user
    target_user.save(update_fields=["name", "department", "position", "use_yn", "updated_by"])
    messages.success(request, "사용자 정보를 수정했습니다.")


@transaction.atomic
def _delete_user(request):
    target_user = _get_target_user_from_post(request, "삭제")
    if target_user is None:
        return

    if target_user.sn == request.user.sn:
        messages.error(request, "현재 로그인한 사용자는 삭제할 수 없습니다.")
        return

    try:
        target_user.delete()
        messages.success(request, "사용자를 삭제했습니다.")
    except ProtectedError:
        target_user.use_yn = YesNoChoices.NO
        target_user.updated_by = request.user
        target_user.save(update_fields=["use_yn", "updated_by"])
        messages.success(request, "연결된 데이터가 있어 사용자를 비활성화했습니다.")


def _role_display_name(role):
    role_code = getattr(role, "role_id", "") or getattr(getattr(role, "role", None), "code", "") or ""
    role_name = getattr(getattr(role, "role", None), "name", "") or ""
    if role_name:
        return role_name
    if role_code == "ROLE_MANAGER":
        return "프로젝트 관리자"
    if role_code == "ROLE_MEMBER":
        return "담당자"
    return role_code or "-"


def _build_user_project_role_payloads(user_rows):
    user_sns = [getattr(user, "sn", None) for user in user_rows]
    user_sns = [user_sn for user_sn in user_sns if user_sn is not None]
    payloads = {str(user_sn): [] for user_sn in user_sns}
    if not user_sns:
        return payloads

    project_roles = (
        ProjectUserRole.objects.filter(
            user_id__in=user_sns,
            project__is_deleted=YesNoChoices.NO,
        )
        .select_related("project", "role")
        .order_by("user_id", "project__sn", "sn")
    )
    for project_role in project_roles:
        role_code = project_role.role_id or ""
        payloads.setdefault(str(project_role.user_id), []).append(
            {
                "projectName": project_role.project.name,
                "roleCode": role_code,
                "roleName": _role_display_name(project_role),
            }
        )
    return payloads


@login_required(login_url="home")
def temp_password_notice(request):
    if request.user.tmpr_pswd_yn != YesNoChoices.YES:
        return redirect(_pop_temp_password_redirect_url(request))
    return render(
        request,
        "users/temp_password_notice.html",
        {
            "title": "임시 비밀번호 안내",
            "profile_url": reverse("user_profile"),
        },
    )


@login_required(login_url="home")
def user_profile(request):
    ensure_initial_reference_data()
    profile_form = _build_profile_form_data(request.user)
    force_password_change = request.user.tmpr_pswd_yn == YesNoChoices.YES

    if request.method == "POST":
        updated, profile_form = _update_profile(request, request.user)
        force_password_change = request.user.tmpr_pswd_yn == YesNoChoices.YES
        if updated:
            return redirect(_pop_temp_password_redirect_url(request))

    context = {
        "active_menu": "",
        "title": "개인 정보 수정",
        "profile_form": profile_form,
        "force_password_change": force_password_change,
    }
    return render(request, "users/profile.html", context)


@login_required(login_url="home")
def user_list(request):
    ensure_initial_reference_data()
    admin_redirect = _require_admin(request)
    if admin_redirect is not None:
        return admin_redirect

    create_form = _build_create_form_data()
    open_user_create_modal = False

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create_user":
            created, create_form = _create_user(request)
            if created:
                return redirect("user_list")
            open_user_create_modal = True
        elif action == "reset_user_password":
            _reset_user_password(request)
            return redirect("user_list")
        elif action == "update_user":
            _update_user(request)
            return redirect("user_list")
        elif action == "delete_user":
            _delete_user(request)
            return redirect("user_list")

    active = request.GET.get("active", "all")
    search_field = request.GET.get("field", "all")
    query = request.GET.get("q", "").strip()

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

    has_users = users.exists()
    paged_users, pagination_context = paginate(request, users if has_users else _demo_users())
    user_rows = list(paged_users.object_list)
    selected_user = users.first() if users.exists() else None

    role_payloads_by_user = _build_user_project_role_payloads(user_rows)
    for user in user_rows:
        user_sn = getattr(user, "sn", None)
        payload = role_payloads_by_user.get(str(user_sn), []) if user_sn is not None else []
        setattr(user, "project_role_json", json.dumps(payload, ensure_ascii=False))

    if selected_user is not None:
        project_roles = (
            ProjectUserRole.objects.filter(user=selected_user, project__is_deleted=YesNoChoices.NO)
            .select_related("project", "role")
            .order_by("project__sn", "sn")
        )
        role_rows = list(project_roles) if project_roles.exists() else []
    else:
        role_rows = [
            {"project": {"name": "AI-DLC Project (예시)"}, "role": {"code": "MANAGER"}},
            {"project": {"name": "Camp Project (예시)"}, "role": {"code": "MEMBER"}},
        ]

    context = {
        "active_menu": "users",
        "users": user_rows,
        **pagination_context,
        "selected_user": selected_user or _demo_users()[0],
        "user_roles": role_rows,
        "active_filter": active,
        "search_field": search_field,
        "query": query,
        "title": "사용자 관리",
        "create_user_form": create_form,
        "open_user_create_modal": open_user_create_modal,
        "suppress_page_messages": open_user_create_modal,
        "temp_password": TEMP_PASSWORD,
    }
    return render(request, "users/user_list.html", context)
