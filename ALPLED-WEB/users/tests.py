from unittest.mock import patch

from django.template.defaultfilters import date as django_date
from django.test import TestCase
from django.urls import reverse

from common.models import YesNoChoices

from .models import User
from .views import (
    DEFAULT_DOCUMENT_CODE,
    RFP_TEMPLATE_FILENAME,
    RFP_TEMPLATE_URI,
    TEMP_PASSWORD,
    TEMP_PASSWORD_REDIRECT_SESSION_KEY,
)


class UserViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.filter(user_id="admin").first()
        if self.admin is None:
            self.admin = User.objects.create_user(
                sn=1,
                user_id="admin",
                password="abc1234",
                name="Admin",
                sys_mngr_yn=YesNoChoices.YES,
                tmpr_pswd_yn=YesNoChoices.NO,
                use_yn=YesNoChoices.YES,
            )
        else:
            self.admin.set_password("abc1234")
            self.admin.name = "Admin"
            self.admin.sys_mngr_yn = YesNoChoices.YES
            self.admin.tmpr_pswd_yn = YesNoChoices.NO
            self.admin.use_yn = YesNoChoices.YES
            self.admin.save(update_fields=["password", "name", "sys_mngr_yn", "tmpr_pswd_yn", "use_yn"])

        self.member = User.objects.filter(user_id="member").first()
        if self.member is None:
            self.member = User.objects.create_user(
                sn=2,
                user_id="member",
                password="abc1234",
                name="Member",
                sys_mngr_yn=YesNoChoices.NO,
                tmpr_pswd_yn=YesNoChoices.NO,
                use_yn=YesNoChoices.YES,
                created_by=self.admin,
                updated_by=self.admin,
            )
        else:
            self.member.set_password("abc1234")
            self.member.name = "Member"
            self.member.sys_mngr_yn = YesNoChoices.NO
            self.member.tmpr_pswd_yn = YesNoChoices.NO
            self.member.use_yn = YesNoChoices.YES
            self.member.created_by = self.admin
            self.member.updated_by = self.admin
            self.member.save(
                update_fields=[
                    "password",
                    "name",
                    "sys_mngr_yn",
                    "tmpr_pswd_yn",
                    "use_yn",
                    "created_by",
                    "updated_by",
                ]
            )

    def _doc_history_url(self):
        return f"{reverse('doc_history_list')}?docs_cd={DEFAULT_DOCUMENT_CODE}"

    def _create_temp_user(self):
        return User.objects.create_user(
            sn=3,
            user_id="tempuser",
            password=TEMP_PASSWORD,
            name="Temp User",
            department="Initial Dept",
            position="Initial Position",
            sys_mngr_yn=YesNoChoices.NO,
            tmpr_pswd_yn=YesNoChoices.YES,
            use_yn=YesNoChoices.YES,
            created_by=self.admin,
            updated_by=self.admin,
        )

    def test_login_view_renders_for_anonymous_user(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/login.html")
        self.assertIn("no-store", response.headers.get("Cache-Control", ""))

    def test_authenticated_home_renders_common_main_page(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home.html")
        self.assertContains(response, "ALPLED 개발 산출물")
        self.assertContains(response, "서비스 사용 흐름")
        self.assertContains(response, "border-blue-500")
        self.assertContains(response, reverse("download_rfp_template"))

    def test_authenticated_user_can_download_rfp_template(self):
        self.client.force_login(self.admin)

        with patch("users.views.read_bytes_from_uri", return_value=b"template-bytes") as mocked_read:
            response = self.client.get(reverse("download_rfp_template"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertEqual(
            response["Content-Disposition"],
            f'attachment; filename="{RFP_TEMPLATE_FILENAME}"',
        )
        self.assertEqual(response.content, b"template-bytes")
        mocked_read.assert_called_once_with(RFP_TEMPLATE_URI)

    def test_authenticated_user_is_logged_out_when_login_page_is_loaded(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/login.html")
        self.assertContains(response, reverse("logout"), html=False)
        self.assertContains(response, "alpledAuthenticatedSession", html=False)

        protected_response = self.client.get(reverse("user_list"))
        self.assertEqual(protected_response.status_code, 302)
        self.assertIn(reverse("home"), protected_response["Location"])

    def test_authenticated_pages_are_not_stored_in_browser_history_cache(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("user_list"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers.get("Cache-Control", ""))
        self.assertContains(response, "alpledAuthenticatedSession", html=False)

    def test_admin_login_redirects_to_home(self):
        response = self.client.post(
            reverse("login"),
            {"user_id": "admin", "password": "abc1234"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("home"))

    def test_admin_login_with_root_referer_redirects_to_home(self):
        response = self.client.post(
            reverse("home"),
            {"user_id": "admin", "password": "abc1234"},
            HTTP_REFERER="http://127.0.0.1:8000/",
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("home"))

    def test_non_admin_login_redirects_to_home(self):
        response = self.client.post(
            reverse("login"),
            {"user_id": "member", "password": "abc1234"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("home"))

    def test_temp_password_login_redirects_to_notice_and_stores_next_url(self):
        temp_user = self._create_temp_user()

        response = self.client.post(
            reverse("login"),
            {
                "user_id": temp_user.user_id,
                "password": TEMP_PASSWORD,
                "next": reverse("project_list"),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("temp_password_notice"))
        self.assertEqual(
            self.client.session[TEMP_PASSWORD_REDIRECT_SESSION_KEY],
            reverse("project_list"),
        )

    def test_temp_password_notice_uses_styled_notice_instead_of_browser_alert(self):
        temp_user = self._create_temp_user()
        self.client.force_login(temp_user)

        response = self.client.get(reverse("temp_password_notice"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/temp_password_notice.html")
        self.assertContains(response, "data-auto-notice", html=False)
        self.assertContains(response, "임시 비밀번호입니다. 비밀번호를 변경해 주세요.")
        self.assertNotContains(response, "alert(", html=False)

    def test_temp_password_user_is_blocked_from_other_pages_until_password_change(self):
        temp_user = self._create_temp_user()
        self.client.force_login(temp_user)

        response = self.client.get(reverse("user_list"), follow=True)

        self.assertRedirects(response, reverse("user_profile"))
        self.assertContains(response, "최초 비밀번호를 수정해주세요.")
        self.assertEqual(
            self.client.session[TEMP_PASSWORD_REDIRECT_SESSION_KEY],
            reverse("user_list"),
        )

    def test_profile_update_changes_name_department_and_position(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("user_profile"),
            {
                "name": "Updated Admin",
                "department": "Platform",
                "position": "Lead",
                "new_password": "",
                "new_password_confirm": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("home"))

        self.admin.refresh_from_db()
        self.assertEqual(self.admin.name, "Updated Admin")
        self.assertEqual(self.admin.department, "Platform")
        self.assertEqual(self.admin.position, "Lead")
        self.assertEqual(self.admin.tmpr_pswd_yn, YesNoChoices.NO)

        home_response = self.client.get(reverse("home"))
        self.assertEqual(home_response.status_code, 200)

        follow_response = self.client.get(reverse("user_profile"))
        self.assertEqual(follow_response.status_code, 200)

        self.admin.refresh_from_db()
        self.assertEqual(self.admin.name, "Updated Admin")
        self.assertEqual(self.admin.department, "Platform")
        self.assertEqual(self.admin.position, "Lead")

    def test_profile_update_allows_blank_department_and_position(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("user_profile"),
            {
                "name": "Updated Admin",
                "department": "",
                "position": "",
                "new_password": "",
                "new_password_confirm": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.name, "Updated Admin")
        self.assertIsNone(self.admin.department)
        self.assertIsNone(self.admin.position)

    def test_profile_page_renders_same_validation_constraints_as_user_modals(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("user_profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="profile-name"', html=False)
        self.assertContains(response, 'pattern="[A-Za-z0-9가-힣_ ]+"', html=False)
        self.assertContains(response, 'title="이름은 한글, 영문, 숫자, 밑줄(_)로 2자 이상 100자 이하로 입력해 주세요."', html=False)
        self.assertContains(response, 'id="profile-department"', html=False)
        self.assertContains(response, 'title="부서는 한글, 영문, 숫자, 밑줄(_)로 최대 100자까지 입력해 주세요."', html=False)
        self.assertContains(response, 'id="profile-position"', html=False)
        self.assertContains(response, 'title="직급은 한글, 영문, 숫자, 밑줄(_)로 최대 100자까지 입력해 주세요."', html=False)

    def test_profile_update_rejects_invalid_name_department_and_position_values(self):
        self.client.force_login(self.admin)
        self.client.get(reverse("user_profile"))
        self.admin.refresh_from_db()
        original_values = (self.admin.name, self.admin.department, self.admin.position)

        invalid_cases = [
            (
                {"name": "A", "department": "Platform", "position": "Lead"},
                "이름은 한글, 영문, 숫자, 밑줄(_)로 최소 2자에서 최대 100자까지 입력할 수 있습니다.",
            ),
            (
                {"name": "Admin", "department": "Platform!", "position": "Lead"},
                "부서는 한글, 영문, 숫자, 밑줄(_)로 최대 100자까지 입력할 수 있습니다.",
            ),
            (
                {"name": "Admin", "department": "Platform", "position": "Lead!"},
                "직급은 한글, 영문, 숫자, 밑줄(_)로 최대 100자까지 입력할 수 있습니다.",
            ),
        ]

        for payload, message in invalid_cases:
            with self.subTest(payload=payload):
                response = self.client.post(
                    reverse("user_profile"),
                    {
                        "new_password": "",
                        "new_password_confirm": "",
                        **payload,
                    },
                    follow=True,
                )

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, message)
                self.admin.refresh_from_db()
                self.assertEqual(
                    (self.admin.name, self.admin.department, self.admin.position),
                    original_values,
                )

    def test_profile_password_change_clears_temp_password_flag_and_keeps_session(self):
        temp_user = self._create_temp_user()
        self.client.force_login(temp_user)
        session = self.client.session
        session[TEMP_PASSWORD_REDIRECT_SESSION_KEY] = reverse("project_list")
        session.save()

        response = self.client.post(
            reverse("user_profile"),
            {
                "name": "Temp User",
                "department": "Security",
                "position": "Engineer",
                "new_password": "newpass123!",
                "new_password_confirm": "newpass123!",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("project_list"))

        temp_user.refresh_from_db()
        self.assertEqual(temp_user.department, "Security")
        self.assertEqual(temp_user.position, "Engineer")
        self.assertEqual(temp_user.tmpr_pswd_yn, YesNoChoices.NO)
        self.assertTrue(temp_user.check_password("newpass123!"))

        follow_response = self.client.get(self._doc_history_url())
        self.assertEqual(follow_response.status_code, 200)

    def test_temp_password_user_cannot_reuse_default_password_on_profile_update(self):
        temp_user = self._create_temp_user()
        self.client.force_login(temp_user)

        response = self.client.post(
            reverse("user_profile"),
            {
                "name": "Temp User",
                "department": "Security",
                "position": "Engineer",
                "new_password": TEMP_PASSWORD,
                "new_password_confirm": TEMP_PASSWORD,
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "임시 비밀번호와 동일한 비밀번호로 변경할 수 없습니다.")

        temp_user.refresh_from_db()
        self.assertEqual(temp_user.tmpr_pswd_yn, YesNoChoices.YES)
        self.assertTrue(temp_user.check_password(TEMP_PASSWORD))

    def test_non_admin_access_to_user_list_redirects_to_home(self):
        self.client.force_login(self.member)

        response = self.client.get(reverse("user_list"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("home"))

    def test_sidebar_console_label_depends_on_user_role(self):
        self.client.force_login(self.admin)
        admin_response = self.client.get(reverse("user_list"))

        self.assertContains(admin_response, "Admin Console")
        self.assertNotContains(admin_response, "User Console")
        self.assertContains(admin_response, f'href="{reverse("home")}"', html=False)

        self.client.force_login(self.member)
        member_response = self.client.get(self._doc_history_url())

        self.assertContains(member_response, "User Console")
        self.assertNotContains(member_response, "Admin Console")

    def test_create_user_inserts_requested_values(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("user_list"),
            {
                "action": "create_user",
                "user_id": "EMP202401",
                "name": "Hong",
                "department": "Development",
                "position": "Manager",
                "use_yn": YesNoChoices.NO,
            },
        )

        self.assertEqual(response.status_code, 302)

        created_user = User.objects.get(user_id="EMP202401")
        self.assertEqual(created_user.name, "Hong")
        self.assertEqual(created_user.department, "Development")
        self.assertEqual(created_user.position, "Manager")
        self.assertEqual(created_user.sys_mngr_yn, YesNoChoices.NO)
        self.assertEqual(created_user.tmpr_pswd_yn, YesNoChoices.YES)
        self.assertEqual(created_user.use_yn, YesNoChoices.NO)
        self.assertTrue(created_user.check_password(TEMP_PASSWORD))

    def test_create_user_allows_blank_department_and_position(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("user_list"),
            {
                "action": "create_user",
                "user_id": "EMP202406",
                "name": "Hong",
                "department": "",
                "position": "",
                "use_yn": YesNoChoices.YES,
            },
        )

        self.assertEqual(response.status_code, 302)

        created_user = User.objects.get(user_id="EMP202406")
        self.assertIsNone(created_user.department)
        self.assertIsNone(created_user.position)

    def test_create_user_allows_numbers_and_underscore_in_user_fields(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("user_list"),
            {
                "action": "create_user",
                "user_id": "skn27_1_1_",
                "name": "skn27 1팀 사용자1",
                "department": "skn27_1",
                "position": "사원",
                "use_yn": YesNoChoices.YES,
            },
        )

        self.assertEqual(response.status_code, 302)

        created_user = User.objects.get(user_id="skn27_1_1_")
        self.assertEqual(created_user.name, "skn27 1팀 사용자1")
        self.assertEqual(created_user.department, "skn27_1")
        self.assertEqual(created_user.position, "사원")

    def test_create_user_validates_registration_constraints(self):
        self.client.force_login(self.admin)

        invalid_cases = [
            (
                {"user_id": "EMP202402", "name": "H", "department": "Development", "position": "Manager"},
                "이름은 한글, 영문, 숫자, 밑줄(_)로 최소 2자에서 최대 100자까지 입력할 수 있습니다.",
            ),
            (
                {"user_id": "EMP202403", "name": "Hong", "department": "Development!", "position": "Manager"},
                "부서는 한글, 영문, 숫자, 밑줄(_)로 최대 100자까지 입력할 수 있습니다.",
            ),
            (
                {"user_id": "EMP202404", "name": "Hong", "department": "Development", "position": "Manager!"},
                "직급은 한글, 영문, 숫자, 밑줄(_)로 최대 100자까지 입력할 수 있습니다.",
            ),
            (
                {"user_id": "EMP20240", "name": "Hong!", "department": "Development", "position": "Manager"},
                "이름은 한글, 영문, 숫자, 밑줄(_)로 최소 2자에서 최대 100자까지 입력할 수 있습니다.",
            ),
            (
                {"user_id": "EMPONLY", "name": "Hong", "department": "Development", "position": "Manager"},
                "사원번호는 영문자, 숫자, 밑줄(_) 조합으로 최소 7자에서 최대 10자까지 입력할 수 있습니다.",
            ),
            (
                {"user_id": "1234567", "name": "Hong", "department": "Development", "position": "Manager"},
                "사원번호는 영문자, 숫자, 밑줄(_) 조합으로 최소 7자에서 최대 10자까지 입력할 수 있습니다.",
            ),
            (
                {"user_id": "EMP-001", "name": "Hong", "department": "Development", "position": "Manager"},
                "사원번호는 영문자, 숫자, 밑줄(_) 조합으로 최소 7자에서 최대 10자까지 입력할 수 있습니다.",
            ),
        ]

        for payload, message in invalid_cases:
            with self.subTest(payload=payload):
                response = self.client.post(
                    reverse("user_list"),
                    {
                        "action": "create_user",
                        "use_yn": YesNoChoices.YES,
                        **payload,
                    },
                    follow=True,
                )

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, message)
                self.assertContains(response, 'data-open-user-create-modal="true"', html=False)
                self.assertFalse(User.objects.filter(user_id=payload["user_id"]).exists())

    def test_update_user_validates_detail_modal_constraints(self):
        self.client.force_login(self.admin)
        original_values = (self.member.name, self.member.department, self.member.position)

        invalid_cases = [
            (
                {"name": "Member!", "department": "Platform", "position": "Lead"},
                "이름은 한글, 영문, 숫자, 밑줄(_)로 최소 2자에서 최대 100자까지 입력할 수 있습니다.",
            ),
            (
                {"name": "Member", "department": "Platform!", "position": "Lead"},
                "부서는 한글, 영문, 숫자, 밑줄(_)로 최대 100자까지 입력할 수 있습니다.",
            ),
            (
                {"name": "Member", "department": "Platform", "position": "Lead!"},
                "직급은 한글, 영문, 숫자, 밑줄(_)로 최대 100자까지 입력할 수 있습니다.",
            ),
        ]

        for payload, message in invalid_cases:
            with self.subTest(payload=payload):
                response = self.client.post(
                    reverse("user_list"),
                    {
                        "action": "update_user",
                        "user_sn": str(self.member.sn),
                        "use_yn": YesNoChoices.YES,
                        **payload,
                    },
                    follow=True,
                )

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, message)
                self.member.refresh_from_db()
                self.assertEqual(
                    (self.member.name, self.member.department, self.member.position),
                    original_values,
                )

    def test_update_user_allows_blank_department_and_position(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("user_list"),
            {
                "action": "update_user",
                "user_sn": str(self.member.sn),
                "name": "Updated Member",
                "department": "",
                "position": "",
                "use_yn": YesNoChoices.YES,
            },
        )

        self.assertEqual(response.status_code, 302)

        self.member.refresh_from_db()
        self.assertEqual(self.member.name, "Updated Member")
        self.assertIsNone(self.member.department)
        self.assertIsNone(self.member.position)

    def test_create_user_rejects_duplicate_user_id(self):
        self.client.force_login(self.admin)
        User.objects.create_user(
            user_id="EMP202405",
            password=TEMP_PASSWORD,
            name="Already",
            department="Development",
            position="Manager",
            sys_mngr_yn=YesNoChoices.NO,
            tmpr_pswd_yn=YesNoChoices.YES,
            use_yn=YesNoChoices.YES,
            created_by=self.admin,
            updated_by=self.admin,
        )

        response = self.client.post(
            reverse("user_list"),
            {
                "action": "create_user",
                "user_id": "EMP202405",
                "name": "Hong",
                "department": "Development",
                "position": "Manager",
                "use_yn": YesNoChoices.YES,
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "이미 존재하는 사원번호입니다.")
        self.assertEqual(User.objects.filter(user_id="EMP202405").count(), 1)

    def test_user_list_renders_reset_password_button_in_detail_modal(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("user_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="action" value="reset_user_password"', html=False)
        self.assertContains(response, 'name="action" value="update_user"', html=False)
        self.assertContains(response, 'name="action" value="delete_user"', html=False)
        self.assertContains(response, "data-confirm-form", html=False)

    def test_user_list_detail_modal_formats_created_at_and_hides_last_login(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("user_list"))

        expected_created_at = django_date(self.admin.created_at, "Y-m-d H:i:s")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'value="{expected_created_at}"', html=False)
        self.assertContains(response, f'data-user-created-at="{expected_created_at}"', html=False)
        self.assertNotContains(response, "마지막 로그인 일자")

    def test_user_create_form_uses_server_styled_validation_messages(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("user_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<form method=\"post\" novalidate data-user-create-form>", html=False)

    def test_reset_user_password_sets_temp_flag_and_default_password(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("user_list"),
            {
                "action": "reset_user_password",
                "user_sn": str(self.member.sn),
            },
        )

        self.assertEqual(response.status_code, 302)

        self.member.refresh_from_db()
        self.assertEqual(self.member.tmpr_pswd_yn, YesNoChoices.YES)
        self.assertTrue(self.member.check_password(TEMP_PASSWORD))

    def test_update_user_changes_detail_values(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("user_list"),
            {
                "action": "update_user",
                "user_sn": str(self.member.sn),
                "name": "Updated Member",
                "department": "QA",
                "position": "Lead",
                "use_yn": YesNoChoices.NO,
            },
        )

        self.assertEqual(response.status_code, 302)

        self.member.refresh_from_db()
        self.assertEqual(self.member.name, "Updated Member")
        self.assertEqual(self.member.department, "QA")
        self.assertEqual(self.member.position, "Lead")
        self.assertEqual(self.member.use_yn, YesNoChoices.NO)
        self.assertEqual(self.member.updated_by, self.admin)

    def test_delete_user_removes_user_when_not_protected(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("user_list"),
            {
                "action": "delete_user",
                "user_sn": str(self.member.sn),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(sn=self.member.sn).exists())

    def test_delete_current_user_is_blocked(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("user_list"),
            {
                "action": "delete_user",
                "user_sn": str(self.admin.sn),
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "현재 로그인한 사용자는 삭제할 수 없습니다.")
        self.assertTrue(User.objects.filter(sn=self.admin.sn).exists())

    def test_resetting_own_password_keeps_session_and_requires_password_change(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("user_list"),
            {
                "action": "reset_user_password",
                "user_sn": str(self.admin.sn),
            },
        )

        self.assertEqual(response.status_code, 302)
        blocked_response = self.client.get(reverse("user_list"))
        self.assertEqual(blocked_response.status_code, 302)
        self.assertEqual(blocked_response["Location"], reverse("user_profile"))

        self.admin.refresh_from_db()
        self.assertEqual(self.admin.tmpr_pswd_yn, YesNoChoices.YES)
        self.assertTrue(self.admin.check_password(TEMP_PASSWORD))

    def test_sidebar_hides_admin_links_for_non_admin_user(self):
        self.client.force_login(self.member)

        response = self.client.get(self._doc_history_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, f'href="{reverse("user_list")}"', html=False)
        self.assertNotContains(response, f'href="{reverse("project_list")}"', html=False)

    def test_sidebar_profile_block_contains_click_affordance(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("user_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-profile-url=", html=False)
        self.assertContains(response, "cursor-pointer", html=False)
