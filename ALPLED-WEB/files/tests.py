import shutil
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from common.models import Code, YesNoChoices
from common.storage import build_s3_uri, save_bytes
from docs.models import Document
from projects.models import Project, ProjectUserRole
from users.models import User

from .models import ProjectFile


class FileListViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.filter(user_id="admin").first()
        if self.user is None:
            self.user = User.objects.create_user(
                sn=1,
                user_id="admin",
                password="abc1234",
                name="Admin",
                sys_mngr_yn="Y",
                use_yn="Y",
            )
        else:
            self.user.set_password("abc1234")
            self.user.save(update_fields=["password"])
        self.client.force_login(self.user)

        self.role_member, _ = Code.objects.get_or_create(
            code="ROLE_MEMBER",
            defaults={
                "name": "멤버",
                "created_by": self.user,
                "updated_by": self.user,
            },
        )
        self.role_manager, _ = Code.objects.get_or_create(
            code="ROLE_MANAGER",
            defaults={
                "name": "관리자",
                "created_by": self.user,
                "updated_by": self.user,
            },
        )
        self.rfp_code, _ = Code.objects.get_or_create(
            code="FILE_RFP",
            defaults={
                "name": "RFP",
                "created_by": self.user,
                "updated_by": self.user,
            },
        )
        self.meeting_code, _ = Code.objects.get_or_create(
            code="FILE_MEETING",
            defaults={
                "name": "회의록",
                "created_by": self.user,
                "updated_by": self.user,
            },
        )

        self.project = self._create_project(1, "First Project")
        self._grant_project_role(1, self.project, self.role_manager)
        self.temp_dir = Path.cwd() / ".tmp-test-storage" / self._testMethodName
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_project(self, sn, name, is_deleted=YesNoChoices.NO):
        return Project.objects.create(
            sn=sn,
            name=name,
            is_deleted=is_deleted,
            created_by=self.user,
            updated_by=self.user,
        )

    def _grant_project_role(self, sn, project, role):
        return ProjectUserRole.objects.create(
            sn=sn,
            project=project,
            user=self.user,
            role=role,
            created_by=self.user,
            updated_by=self.user,
        )

    def _create_stored_project_file(self, sn, name, content_bytes, *, file_type=None):
        storage_key = f"project-files/{self.project.sn}/{sn}-{name}"
        save_bytes(storage_key, content_bytes)
        return ProjectFile.objects.create(
            sn=sn,
            project=self.project,
            file_type=file_type or self.rfp_code,
            name=name,
            path=build_s3_uri(storage_key),
            size=len(content_bytes),
            extension=name.split(".")[-1][:4],
            created_by=self.user,
            updated_by=self.user,
        )

    def test_upload_files_creates_project_files(self):
        with self.settings(ALPLED_LOCAL_STORAGE_ROOT=self.temp_dir):
            response = self.client.post(
                reverse("file_list"),
                {
                    "action": "upload",
                    "project_sn": self.project.sn,
                    "rfp_files": [
                        SimpleUploadedFile(
                            "proposal.pdf",
                            b"rfp-content",
                            content_type="application/pdf",
                        )
                    ],
                    "meeting_files": [
                        SimpleUploadedFile(
                            "meeting.docx",
                            b"meeting-content",
                            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        )
                    ],
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ProjectFile.objects.count(), 2)
        self.assertTrue(ProjectFile.objects.filter(file_type=self.rfp_code).exists())
        self.assertTrue(ProjectFile.objects.filter(file_type=self.meeting_code).exists())
        self.assertTrue(ProjectFile.objects.filter(path__startswith="s3://").exists())

    def test_upload_rejects_hwp_files(self):
        with self.settings(ALPLED_LOCAL_STORAGE_ROOT=self.temp_dir):
            response = self.client.post(
                reverse("file_list"),
                {
                    "action": "upload",
                    "project_sn": self.project.sn,
                    "rfp_files": [
                        SimpleUploadedFile(
                            "proposal.hwp",
                            b"hwp-content",
                            content_type="application/x-hwp",
                        )
                    ],
                },
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ProjectFile.objects.count(), 0)
        messages = [message.message for message in response.context["messages"]]
        self.assertIn("업로드 가능한 파일 형식은 .docx, .pdf 입니다.", messages)

    def test_file_upload_form_lists_docx_and_pdf_only(self):
        response = self.client.get(reverse("file_list"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("허용 파일 형식: .docx, .pdf", content)
        self.assertIn('accept=".docx,.pdf"', content)
        self.assertNotIn(".hwp", content)

    def test_search_filters_files_by_type_and_name(self):
        ProjectFile.objects.create(
            sn=1,
            project=self.project,
            file_type=self.rfp_code,
            name="RFP_20260520.pdf",
            path=build_s3_uri(f"project-files/{self.project.sn}/1-RFP_20260520.pdf"),
            size=3,
            extension="pdf",
            created_by=self.user,
            updated_by=self.user,
        )
        ProjectFile.objects.create(
            sn=2,
            project=self.project,
            file_type=self.meeting_code,
            name="meeting_20260520.docx",
            path=build_s3_uri(f"project-files/{self.project.sn}/2-meeting_20260520.docx"),
            size=7,
            extension="docx",
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.get(
            reverse("file_list"),
            {
                "file_type": "RFP",
                "field": "name",
                "q": "RFP_20260520",
            },
        )

        self.assertEqual(response.status_code, 200)
        documents = response.context["documents"]
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["name"], "RFP_20260520.pdf")

    def test_file_list_only_shows_rfp_and_meeting_files(self):
        other_code, _ = Code.objects.get_or_create(
            code="FILE_ETC",
            defaults={
                "name": "Etc",
                "created_by": self.user,
                "updated_by": self.user,
            },
        )
        ProjectFile.objects.create(
            sn=1,
            project=self.project,
            file_type=self.rfp_code,
            name="RFP_20260520.pdf",
            path=build_s3_uri(f"project-files/{self.project.sn}/1-RFP_20260520.pdf"),
            size=3,
            extension="pdf",
            created_by=self.user,
            updated_by=self.user,
        )
        ProjectFile.objects.create(
            sn=2,
            project=self.project,
            file_type=self.meeting_code,
            name="meeting_20260520.docx",
            path=build_s3_uri(f"project-files/{self.project.sn}/2-meeting_20260520.docx"),
            size=7,
            extension="docx",
            created_by=self.user,
            updated_by=self.user,
        )
        ProjectFile.objects.create(
            sn=3,
            project=self.project,
            file_type=other_code,
            name="other_20260520.pdf",
            path=build_s3_uri(f"project-files/{self.project.sn}/3-other_20260520.pdf"),
            size=5,
            extension="pdf",
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.get(reverse("file_list"))

        self.assertEqual(response.status_code, 200)
        document_names = [document["name"] for document in response.context["documents"]]
        self.assertEqual(document_names, ["meeting_20260520.docx", "RFP_20260520.pdf"])

    def test_delete_and_download_selected_files(self):
        with self.settings(ALPLED_LOCAL_STORAGE_ROOT=self.temp_dir):
            project_file = self._create_stored_project_file(1, "proposal.pdf", b"download-me")

            download_response = self.client.post(
                reverse("file_list"),
                {
                    "action": "download",
                    "project_sn": self.project.sn,
                    "selected_files": [project_file.sn],
                },
            )
            self.assertEqual(download_response.status_code, 200)
            self.assertIn("attachment;", download_response["Content-Disposition"])
            self.assertEqual(download_response.content, b"download-me")

            delete_response = self.client.post(
                reverse("file_list"),
                {
                    "action": "delete",
                    "project_sn": self.project.sn,
                    "selected_files": [project_file.sn],
                },
            )
        self.assertEqual(delete_response.status_code, 302)
        self.assertFalse(ProjectFile.objects.filter(sn=project_file.sn).exists())

    def test_download_reads_uploaded_file_from_s3_uri_path(self):
        with self.settings(ALPLED_LOCAL_STORAGE_ROOT=self.temp_dir):
            self.client.post(
                reverse("file_list"),
                {
                    "action": "upload",
                    "project_sn": self.project.sn,
                    "rfp_files": [
                        SimpleUploadedFile(
                            "proposal.pdf",
                            b"stored-download",
                            content_type="application/pdf",
                        )
                    ],
                },
            )

            project_file = ProjectFile.objects.get()
            response = self.client.post(
                reverse("file_list"),
                {
                    "action": "download",
                    "project_sn": self.project.sn,
                    "selected_files": [project_file.sn],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"stored-download")

    def test_download_rejects_legacy_non_s3_path(self):
        project_file = ProjectFile.objects.create(
            sn=1,
            project=self.project,
            file_type=self.rfp_code,
            name="proposal.pdf",
            path="proposal.pdf",
            size=11,
            extension="pdf",
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.post(
            reverse("file_list"),
            {
                "action": "download",
                "project_sn": self.project.sn,
                "selected_files": [project_file.sn],
            },
        )

        self.assertEqual(response.status_code, 302)

    def test_sidebar_lists_only_accessible_non_deleted_projects(self):
        member_project = self._create_project(2, "Member Project")
        deleted_project = self._create_project(3, "Deleted Project", is_deleted=YesNoChoices.YES)
        self._create_project(4, "Unassigned Project")

        self._grant_project_role(2, member_project, self.role_member)
        self._grant_project_role(3, deleted_project, self.role_manager)

        response = self.client.get(reverse("file_list"))

        self.assertEqual(response.status_code, 200)
        available_names = [project.name for project in response.context["available_projects"]]
        self.assertEqual(available_names, ["First Project", "Member Project"])
        self.assertEqual(response.context["current_project"].name, "First Project")

    def test_set_current_project_updates_session_selection(self):
        second_project = self._create_project(2, "Second Project")
        self._grant_project_role(2, second_project, self.role_member)

        response = self.client.post(
            reverse("set_current_project"),
            {
                "project_sn": second_project.sn,
                "next": reverse("file_list"),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("file_list"))

        follow_up = self.client.get(reverse("file_list"))
        self.assertEqual(follow_up.context["current_project"].name, "Second Project")

    def test_set_current_project_redirects_document_detail_to_document_type_entry(self):
        second_project = self._create_project(2, "Second Project")
        self._grant_project_role(2, second_project, self.role_member)
        srs_code, _ = Code.objects.get_or_create(
            code="DOC_SRS",
            defaults={"name": "사용자 요구사항 정의서", "created_by": self.user, "updated_by": self.user},
        )
        progress_code, _ = Code.objects.get_or_create(
            code="PRGRS_COMPLETED",
            defaults={"name": "생성 완료", "created_by": self.user, "updated_by": self.user},
        )
        document = Document.objects.create(
            sn=137,
            project=self.project,
            document_type=srs_code,
            progress_status=progress_code,
            version="1.0",
            modification_content="저장",
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.post(
            reverse("set_current_project"),
            {
                "project_sn": second_project.sn,
                "next": f"{reverse('doc_detail', args=[document.sn])}?mode=view",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{reverse('doc_generate')}?docs_cd=DOC_SRS&resume=1")
