from django.test import TestCase
from django.urls import reverse
from urllib.parse import quote

from common.models import Code, YesNoChoices
from common.project_selection import get_available_projects_for_user
from projects.models import Project, ProjectUserRole
from users.models import User


class ProjectListAccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.filter(user_id="admin").first()
        if self.admin is None:
            self.admin = User.objects.create_user(
                sn=1,
                user_id="admin",
                password="abc1234",
                name="Admin",
                sys_mngr_yn=YesNoChoices.YES,
                use_yn=YesNoChoices.YES,
            )
        else:
            self.admin.set_password("abc1234")
            self.admin.sys_mngr_yn = YesNoChoices.YES
            self.admin.use_yn = YesNoChoices.YES
            self.admin.save(update_fields=["password", "sys_mngr_yn", "use_yn"])

        self.member = User.objects.filter(user_id="project-member").first()
        if self.member is None:
            self.member = User.objects.create_user(
                sn=2,
                user_id="project-member",
                password="abc1234",
                name="Project Member",
                sys_mngr_yn=YesNoChoices.NO,
                use_yn=YesNoChoices.YES,
                created_by=self.admin,
                updated_by=self.admin,
            )
        else:
            self.member.set_password("abc1234")
            self.member.sys_mngr_yn = YesNoChoices.NO
            self.member.use_yn = YesNoChoices.YES
            self.member.created_by = self.admin
            self.member.updated_by = self.admin
            self.member.save(
                update_fields=["password", "sys_mngr_yn", "use_yn", "created_by", "updated_by"]
            )
        self.role_manager, _ = Code.objects.get_or_create(
            code="ROLE_MANAGER",
            defaults={"name": "관리자", "created_by": self.admin, "updated_by": self.admin},
        )
        self.role_member, _ = Code.objects.get_or_create(
            code="ROLE_MEMBER",
            defaults={"name": "멤버", "created_by": self.admin, "updated_by": self.admin},
        )

    def _doc_history_url(self):
        return f"{reverse('doc_history_list')}?docs_cd=DOC_SRS"

    def test_non_admin_access_to_project_list_redirects_to_document_history(self):
        self.client.force_login(self.member)

        response = self.client.get(reverse("project_list"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self._doc_history_url())

    def test_admin_access_to_project_list_succeeds(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("project_list"))

        self.assertEqual(response.status_code, 200)

    def test_admin_available_projects_include_unassigned_projects(self):
        assigned_project = Project.objects.create(
            sn=1,
            name="Assigned",
            is_deleted=YesNoChoices.NO,
            created_by=self.admin,
            updated_by=self.admin,
        )
        unassigned_project = Project.objects.create(
            sn=2,
            name="Unassigned",
            is_deleted=YesNoChoices.NO,
            created_by=self.admin,
            updated_by=self.admin,
        )
        deleted_project = Project.objects.create(
            sn=3,
            name="Deleted",
            is_deleted=YesNoChoices.YES,
            created_by=self.admin,
            updated_by=self.admin,
        )
        ProjectUserRole.objects.create(
            sn=1,
            project=assigned_project,
            user=self.admin,
            role=self.role_manager,
            created_by=self.admin,
            updated_by=self.admin,
        )

        projects = list(get_available_projects_for_user(self.admin))

        self.assertIn(assigned_project, projects)
        self.assertIn(unassigned_project, projects)
        self.assertNotIn(deleted_project, projects)

    def test_admin_can_open_project_edit_modal_with_prefilled_data(self):
        project = Project.objects.create(
            sn=1,
            name="Alpha",
            is_deleted=YesNoChoices.NO,
            created_by=self.admin,
            updated_by=self.admin,
        )
        ProjectUserRole.objects.create(
            sn=1,
            project=project,
            user=self.admin,
            role=self.role_manager,
            created_by=self.admin,
            updated_by=self.admin,
        )
        ProjectUserRole.objects.create(
            sn=2,
            project=project,
            user=self.member,
            role=self.role_member,
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("project_list"),
            {"open_project_form": "1", "project_form_mode": "edit", "project_sn": project.sn},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["open_project_form"])
        self.assertEqual(response.context["project_form_mode"], "edit")
        self.assertEqual(response.context["project_form_name"], "Alpha")
        self.assertEqual(response.context["project_form_manager_users"][0]["user_id"], self.admin.user_id)
        self.assertEqual(response.context["project_form_member_users"][0]["user_id"], self.member.user_id)
        self.assertContains(response, 'value="update_project"', html=False)
        self.assertContains(response, 'data-project-delete-submit', html=False)
        self.assertContains(response, "수정")

    def test_project_list_shows_all_manager_names_and_preserves_filter_in_edit_url(self):
        other_manager = User.objects.create_user(
            user_id="manager02",
            password="abc1234",
            name="Second Manager",
            sys_mngr_yn=YesNoChoices.NO,
            use_yn=YesNoChoices.YES,
            created_by=self.admin,
            updated_by=self.admin,
        )
        project = Project.objects.create(
            sn=1,
            name="Alpha",
            is_deleted=YesNoChoices.NO,
            created_by=self.admin,
            updated_by=self.admin,
        )
        ProjectUserRole.objects.create(
            project=project,
            user=self.admin,
            role=self.role_manager,
            created_by=self.admin,
            updated_by=self.admin,
        )
        ProjectUserRole.objects.create(
            project=project,
            user=other_manager,
            role=self.role_manager,
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.client.force_login(self.admin)

        response = self.client.get(reverse("project_list"), {"field": "manager", "q": self.admin.name})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"{self.admin.name}, Second Manager")
        encoded_query = quote(self.admin.name)
        self.assertContains(
            response,
            f"field=manager&amp;q={encoded_query}&amp;open_project_form=1",
            html=False,
        )

    def test_admin_can_update_project_name_and_members(self):
        project = Project.objects.create(
            sn=1,
            name="Alpha",
            is_deleted=YesNoChoices.NO,
            created_by=self.admin,
            updated_by=self.admin,
        )
        ProjectUserRole.objects.create(
            sn=1,
            project=project,
            user=self.admin,
            role=self.role_manager,
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("project_list"),
            {
                "action": "update_project",
                "project_sn": project.sn,
                "project_name": "Beta",
                "manager_user_ids": self.admin.user_id,
                "member_user_ids": self.member.user_id,
                "next": f"{reverse('project_list')}?field=manager&q=Admin",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{reverse('project_list')}?field=manager&q=Admin")
        project.refresh_from_db()
        self.assertEqual(project.name, "Beta")
        self.assertTrue(
            ProjectUserRole.objects.filter(project=project, user=self.member, role=self.role_member).exists()
        )

    def test_admin_can_soft_delete_project(self):
        project = Project.objects.create(
            sn=1,
            name="Alpha",
            is_deleted=YesNoChoices.NO,
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("project_list"),
            {
                "action": "delete_project",
                "project_sn": project.sn,
            },
        )

        self.assertEqual(response.status_code, 302)
        project.refresh_from_db()
        self.assertEqual(project.is_deleted, YesNoChoices.YES)
        self.assertEqual(project.updated_by, self.admin)

        list_response = self.client.get(reverse("project_list"))
        self.assertNotContains(list_response, "Alpha")
