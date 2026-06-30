import shutil
import tempfile
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from common.models import Code, YesNoChoices
from common.storage import build_s3_uri, save_bytes
from files.models import ProjectFile
from projects.models import Project, ProjectNet, ProjectUserRole
from users.models import User

from .models import Document, DocumentApproval, DocumentDetail, GenerationJob
from .services import (
    build_approval_review_view,
    build_document_detail_url,
    build_generation_request_payload,
    extract_text_from_docx,
    get_document_detail_bytes,
    get_generation_state,
    get_onlyoffice_document_server_url,
    request_fastapi_approval_review,
    request_fastapi_generate,
    start_initial_generation_job,
)


class ApprovalReviewJsonDiffTests(SimpleTestCase):
    def test_generic_diff_matches_requirements_by_identifier(self):
        before = {
            "requirements": [
                {"requirement_id": "SFR-001", "priority": "상", "description": "기존 내용"},
                {"requirement_id": "SFR-002", "priority": "중", "description": "유지 내용"},
            ]
        }
        after = {
            "requirements": [
                {"requirement_id": "SFR-002", "priority": "중", "description": "유지 내용"},
                {"requirement_id": "SFR-001", "priority": "최상", "description": "변경 내용"},
            ]
        }

        review = build_approval_review_view({}, before_data=before, after_data=after)

        self.assertEqual(len(review["changes"]), 2)
        paths = {change["target_path"] for change in review["changes"]}
        self.assertIn("data.requirements[requirement_id=SFR-001].priority", paths)
        self.assertIn("data.requirements[requirement_id=SFR-001].description", paths)
        self.assertEqual(review["change_summary"]["modified_count"], 2)

    def test_generic_diff_handles_architecture_component_addition(self):
        before = {"components": [{"component_id": "WEB-01", "name": "Web"}]}
        after = {
            "components": [
                {"component_id": "WEB-01", "name": "Web"},
                {"component_id": "API-01", "name": "API"},
            ]
        }

        review = build_approval_review_view(None, before_data=before, after_data=after)

        self.assertEqual(len(review["changes"]), 1)
        self.assertEqual(review["changes"][0]["change_type"], "added")
        self.assertIn("component_id=API-01", review["changes"][0]["target_path"])


class FastapiRequestHeaderTests(SimpleTestCase):
    class _DummyResponse:
        status_code = 200

        def __init__(self, body):
            self.text = body.decode("utf-8")

        def raise_for_status(self):
            return None

    class _DummySession:
        def __init__(self, captured, response_body):
            self.captured = captured
            self.response_body = response_body
            self.trust_env = True

        def __enter__(self):
            self.captured["session"] = self
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json=None, headers=None, timeout=None):
            self.captured["url"] = url
            self.captured["json"] = json
            self.captured["headers"] = headers or {}
            self.captured["timeout"] = timeout
            self.captured["trust_env"] = self.trust_env
            return FastapiRequestHeaderTests._DummyResponse(self.response_body)

    def test_generate_request_includes_bearer_authorization_header(self):
        captured = {}
        response_body = b'{"status":"accepted"}'

        with self.settings(FASTAPI_BASE_URL="https://example.runpod.net", FASTAPI_API_KEY="rpa_test_key"):
            with patch("docs.services.requests.Session", return_value=self._DummySession(captured, response_body)):
                response = request_fastapi_generate({"project_sn": 1, "docs_cd": "DOC_SRS"})

        self.assertEqual(response["status"], "accepted")
        headers = {key.lower(): value for key, value in captured["headers"].items()}
        self.assertEqual(headers["authorization"], "Bearer rpa_test_key")
        self.assertEqual(headers["content-type"], "application/json")
        self.assertEqual(headers["user-agent"], "ALPLED-WEB/1.0 (Django; requests)")
        self.assertTrue(headers["accept"].startswith("application/json"))
        self.assertFalse(captured["trust_env"])

    def test_approval_review_request_includes_bearer_authorization_header(self):
        captured = {}
        response_body = b'{"status":"accepted"}'

        with self.settings(FASTAPI_BASE_URL="https://example.runpod.net", FASTAPI_API_KEY="rpa_test_key"):
            with patch("docs.services.requests.Session", return_value=self._DummySession(captured, response_body)):
                response = request_fastapi_approval_review(12)

        self.assertEqual(response["status"], "accepted")
        headers = {key.lower(): value for key, value in captured["headers"].items()}
        self.assertEqual(headers["authorization"], "Bearer rpa_test_key")
        self.assertEqual(headers["content-type"], "application/json")
        self.assertEqual(headers["user-agent"], "ALPLED-WEB/1.0 (Django; requests)")
        self.assertFalse(captured["trust_env"])

    def test_approval_review_request_omits_authorization_header_without_api_key(self):
        captured = {}
        response_body = b'{"status":"accepted"}'

        with self.settings(FASTAPI_BASE_URL="https://example.runpod.net", FASTAPI_API_KEY=""):
            with patch("docs.services.requests.Session", return_value=self._DummySession(captured, response_body)):
                response = request_fastapi_approval_review(12)

        self.assertEqual(response["status"], "accepted")
        headers = {key.lower(): value for key, value in captured["headers"].items()}
        self.assertNotIn("authorization", headers)
        self.assertEqual(headers["content-type"], "application/json")
        self.assertEqual(headers["user-agent"], "ALPLED-WEB/1.0 (Django; requests)")


class DocumentWorkflowViewTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS tbl_generation_job (
                    job_sn integer PRIMARY KEY,
                    job_id varchar(36) NOT NULL UNIQUE,
                    prj_sn integer NOT NULL,
                    docs_cd varchar(100) NOT NULL,
                    docs_sn integer NULL,
                    job_stts_cd varchar(100) NOT NULL DEFAULT 'PRGRS_PENDING',
                    progress_rate integer NOT NULL DEFAULT 0,
                    request_json text NOT NULL,
                    result_json text NULL,
                    error_cd varchar(100) NULL,
                    error_msg text NULL,
                    retry_cnt integer NOT NULL DEFAULT 0,
                    max_retry_cnt integer NOT NULL DEFAULT 1,
                    active_key varchar(200) NULL,
                    request_id varchar(100) NULL,
                    requested_dt datetime NOT NULL,
                    started_dt datetime NULL,
                    completed_dt datetime NULL,
                    heartbeat_dt datetime NULL,
                    updated_dt datetime NOT NULL
                )
                """
            )

    @classmethod
    def tearDownClass(cls):
        try:
            with connection.cursor() as cursor:
                cursor.execute("DROP TABLE IF EXISTS tbl_generation_job")
        finally:
            super().tearDownClass()

    def setUp(self):
        self.user = User.objects.filter(user_id="admin").first()
        if self.user is None:
            self.user = User.objects.create_user(
                sn=1,
                user_id="admin",
                password="abc1234",
                name="Admin",
                sys_mngr_yn=YesNoChoices.YES,
                use_yn=YesNoChoices.YES,
            )
        else:
            self.user.set_password("abc1234")
            self.user.use_yn = YesNoChoices.YES
            self.user.save(update_fields=["password", "use_yn"])
        self.client.force_login(self.user)
        self.other_user = User.objects.filter(user_id="doc-member").first()
        if self.other_user is None:
            self.other_user = User.objects.create_user(
                sn=99,
                user_id="doc-member",
                password="abc1234",
                name="Doc Member",
                sys_mngr_yn=YesNoChoices.NO,
                use_yn=YesNoChoices.YES,
                created_by=self.user,
                updated_by=self.user,
            )
        else:
            self.other_user.set_password("abc1234")
            self.other_user.sys_mngr_yn = YesNoChoices.NO
            self.other_user.use_yn = YesNoChoices.YES
            self.other_user.created_by = self.user
            self.other_user.updated_by = self.user
            self.other_user.save(
                update_fields=["password", "sys_mngr_yn", "use_yn", "created_by", "updated_by"]
            )
        self.temp_dir = Path(tempfile.gettempdir()) / "alpled-web-docs-tests" / self._testMethodName
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.storage_override = self.settings(ALPLED_LOCAL_STORAGE_ROOT=self.temp_dir)
        self.storage_override.enable()

        self.role_manager, _ = Code.objects.get_or_create(
            code="ROLE_MANAGER",
            defaults={"name": "관리자", "created_by": self.user, "updated_by": self.user},
        )
        self.role_member, _ = Code.objects.get_or_create(
            code="ROLE_MEMBER",
            defaults={"name": "멤버", "created_by": self.user, "updated_by": self.user},
        )

        self.srs_code, _ = Code.objects.get_or_create(
            code="DOC_SRS",
            defaults={"name": "사용자 요구사항 정의서", "created_by": self.user, "updated_by": self.user},
        )
        self.itf_code, _ = Code.objects.get_or_create(
            code="DOC_ITF",
            defaults={"name": "사용자 인터페이스 설계서", "created_by": self.user, "updated_by": self.user},
        )
        self.arch_code, _ = Code.objects.get_or_create(
            code="DOC_ARCH",
            defaults={"name": "아키텍처 설계서", "created_by": self.user, "updated_by": self.user},
        )
        self.erd_code, _ = Code.objects.get_or_create(
            code="DOC_ERD",
            defaults={"name": "엔티티 관계 모형 설계서", "created_by": self.user, "updated_by": self.user},
        )
        self.db_code, _ = Code.objects.get_or_create(
            code="DOC_DB",
            defaults={"name": "데이터베이스 설계서", "created_by": self.user, "updated_by": self.user},
        )
        self.ts_code, _ = Code.objects.get_or_create(
            code="DOC_TS",
            defaults={"name": "통합 시험 시나리오", "created_by": self.user, "updated_by": self.user},
        )

        self.file_rfp_code, _ = Code.objects.get_or_create(
            code="FILE_RFP",
            defaults={"name": "제안요청서(RFP)", "created_by": self.user, "updated_by": self.user},
        )
        self.file_meeting_code, _ = Code.objects.get_or_create(
            code="FILE_MEETING",
            defaults={"name": "회의록", "created_by": self.user, "updated_by": self.user},
        )
        self.progress_pending, _ = Code.objects.get_or_create(
            code="PRGRS_PENDING",
            defaults={"name": "생성 대기", "created_by": self.user, "updated_by": self.user},
        )
        self.progress_processing, _ = Code.objects.get_or_create(
            code="PRGRS_PROCESSING",
            defaults={"name": "생성 중", "created_by": self.user, "updated_by": self.user},
        )
        self.progress_completed, _ = Code.objects.get_or_create(
            code="PRGRS_COMPLETED",
            defaults={"name": "생성 완료", "created_by": self.user, "updated_by": self.user},
        )
        self.progress_failed, _ = Code.objects.get_or_create(
            code="PRGRS_FAILED",
            defaults={"name": "생성 실패", "created_by": self.user, "updated_by": self.user},
        )

        self.approval_requested, _ = Code.objects.get_or_create(
            code="APRV_REQ",
            defaults={"name": "승인 대기", "created_by": self.user, "updated_by": self.user},
        )
        self.approval_approved, _ = Code.objects.get_or_create(
            code="APRV_COM",
            defaults={"name": "승인 완료", "created_by": self.user, "updated_by": self.user},
        )

        self.project = Project.objects.create(
            sn=1,
            name="First Project",
            is_deleted=YesNoChoices.NO,
            created_by=self.user,
            updated_by=self.user,
        )
        ProjectUserRole.objects.create(
            sn=1,
            project=self.project,
            user=self.user,
            role=self.role_manager,
            created_by=self.user,
            updated_by=self.user,
        )
        ProjectUserRole.objects.create(
            sn=2,
            project=self.project,
            user=self.other_user,
            role=self.role_member,
            created_by=self.user,
            updated_by=self.user,
        )
        session = self.client.session
        session["current_project_sn"] = self.project.sn
        session.save()

    def tearDown(self):
        self.storage_override.disable()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_project_file(self, sn=1, *, code=None, name="proposal.pdf"):
        return ProjectFile.objects.create(
            sn=sn,
            project=self.project,
            file_type=code or self.file_rfp_code,
            name=name,
            path=build_s3_uri(f"project-files/{self.project.sn}/{sn}-{name}"),
            size=12,
            extension=name.split(".")[-1][:4],
            created_by=self.user,
            updated_by=self.user,
        )

    def _create_document(self, sn=1, *, document_type=None, version="1.0", user=None):
        return Document.objects.create(
            sn=sn,
            project=self.project,
            possession_user=user,
            document_type=document_type or self.srs_code,
            version=version,
            modification_content="최초 생성",
            created_by=self.user,
            updated_by=self.user,
        )

    def _create_completed_initial_document(self, sn=1, *, document_type=None):
        document = self._create_document(sn=sn, version="0", document_type=document_type)
        document.progress_status = self.progress_completed
        document.save(update_fields=["progress_status"])
        return document

    def _create_detail(self, sn=1, *, document=None, content=b"docx-binary", path=None):
        storage_key = f"document-details/{document.project.sn}/{document.sn}/{sn}.docx"
        if path is None:
            save_bytes(
                storage_key,
                content,
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            path = build_s3_uri(storage_key)
        return DocumentDetail.objects.create(
            sn=sn,
            document=document,
            path=path,
            is_deleted="N",
            created_by=self.user,
        )

    def _create_project_net(
        self,
        sn=1,
        *,
        project=None,
        name="업무망",
        purpose="내부 업무 처리",
        middleware_stack="Nginx",
        firewall_settings="Allow 443",
        auth_method="SSO",
        expected_concurrent_users=50,
        cloud_yn=YesNoChoices.YES,
        hardware_spec="8core/32GB",
        remarks="기본 비고",
    ):
        return ProjectNet.objects.create(
            sn=sn,
            project=project or self.project,
            name=name,
            purpose=purpose,
            middleware_stack=middleware_stack,
            firewall_settings=firewall_settings,
            auth_method=auth_method,
            expected_concurrent_users=expected_concurrent_users,
            cloud_yn=cloud_yn,
            hardware_spec=hardware_spec,
            remarks=remarks,
            created_by=self.user,
            updated_by=self.user,
        )

    def _create_generation_job(
        self,
        sn=1,
        *,
        job_id=None,
        document_type=None,
        document=None,
        job_status=None,
        request_payload=None,
        result_payload=None,
        error_code=None,
        error_message=None,
        request_id="req-1",
        started_at=None,
    ):
        now = timezone.now()
        return GenerationJob.objects.create(
            sn=sn,
            job_id=job_id or f"job-{sn:04d}",
            project=self.project,
            document_type=document_type or self.srs_code,
            document=document,
            job_status=job_status or self.progress_pending,
            progress_rate=0,
            request_payload=request_payload or {"udt_yn": "N"},
            result_payload=result_payload,
            error_code=error_code,
            error_message=error_message,
            retry_count=0,
            max_retry_count=1,
            active_key=None,
            request_id=request_id,
            requested_at=now,
            started_at=started_at or now,
            completed_at=None,
            heartbeat_at=None,
            updated_at=now,
        )

    def _set_generation_state(
        self,
        *,
        selected_file_ids=None,
        draft_documents=None,
        confirmed_documents=None,
        itf_reference_files=None,
    ):
        session = self.client.session
        session["docs_initial_generation"] = {
            "project_sn": self.project.sn,
            "selected_file_ids": [str(file_id) for file_id in (selected_file_ids or [])],
            "draft_documents": draft_documents or {},
            "confirmed_documents": confirmed_documents or {},
            "itf_reference_files": itf_reference_files or [],
        }
        session.save()

    def _set_doc_job_snapshot(self, **payload):
        session = self.client.session
        session["doc_job_snapshots"] = {
            payload["job_id"]: payload,
        }
        session.save()

    def _prepare_generation_state_until(self, target_code, *, sn_offset=0):
        sequence = [
            ("DOC_SRS", self.srs_code),
            ("DOC_ITF", self.itf_code),
            ("DOC_ARCH", self.arch_code),
            ("DOC_ERD", self.erd_code),
            ("DOC_DB", self.db_code),
            ("DOC_TS", self.ts_code),
        ]
        confirmed_documents = {}
        for index, (code, document_type) in enumerate(sequence, start=sn_offset + 100):
            if code == target_code:
                break
            document = self._create_completed_initial_document(sn=index, document_type=document_type)
            confirmed_documents[code] = document.sn
        self._set_generation_state(confirmed_documents=confirmed_documents)

    def test_history_list_shows_generation_button_before_any_confirmed_document_exists(self):
        response = self.client.get(reverse("doc_history_list"), {"docs_cd": "DOC_ITF"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_document_code"], "DOC_ITF")
        self.assertTrue(response.context["can_generate"])

    def test_history_list_keeps_generation_button_until_all_document_types_exist(self):
        for index, code in enumerate([self.srs_code, self.itf_code, self.arch_code, self.erd_code, self.db_code], start=1):
            self._create_document(sn=index, version="1.0", document_type=code)

        partial_response = self.client.get(reverse("doc_history_list"), {"docs_cd": "DOC_TS"})

        self.assertEqual(partial_response.status_code, 200)
        self.assertTrue(partial_response.context["can_generate"])

        self._create_document(sn=6, version="1.0", document_type=self.ts_code)
        completed_response = self.client.get(reverse("doc_history_list"), {"docs_cd": "DOC_TS"})

        self.assertEqual(completed_response.status_code, 200)
        self.assertFalse(completed_response.context["can_generate"])

    def test_generate_view_shows_latest_previews_when_all_document_types_exist(self):
        latest_srs = None
        for index, code in enumerate(
            [self.srs_code, self.itf_code, self.arch_code, self.erd_code, self.db_code, self.ts_code],
            start=1,
        ):
            document = self._create_document(sn=index, version="1.0", document_type=code)
            document.progress_status = self.progress_completed
            document.save(update_fields=["progress_status"])
            if code == self.srs_code:
                latest_srs = document

        response = self.client.get(reverse("doc_generate"), {"docs_cd": "DOC_SRS", "resume": "1"})

        self.assertEqual(response.status_code, 200)
        progress_by_code = {row["code"]: row for row in response.context["progress_rows"]}
        self.assertEqual(progress_by_code["DOC_SRS"]["document_sn"], latest_srs.sn)
        self.assertContains(response, reverse("doc_detail", args=[latest_srs.sn]), html=False)
        self.assertContains(response, "미리보기")
        self.assertNotContains(response, "현재 프로젝트에 할당된 구성원만")

    def test_history_list_excludes_version_zero_and_keeps_latest_duplicate_version(self):
        self._create_document(sn=1, version="1.0", document_type=self.srs_code)
        newer = self._create_document(sn=2, version="1.0", document_type=self.srs_code)
        self._create_document(sn=3, version="0", document_type=self.srs_code)

        response = self.client.get(reverse("doc_history_list"), {"docs_cd": "DOC_SRS"})

        self.assertEqual(response.status_code, 200)
        documents = response.context["documents"]
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["sn"], newer.sn)

    def test_generate_state_hydration_uses_latest_completed_document(self):
        initial_srs = self._create_document(sn=1, version="0", document_type=self.srs_code)
        initial_srs.progress_status = self.progress_completed
        initial_srs.save(update_fields=["progress_status"])
        approved_srs = self._create_document(sn=10, version="1.0", document_type=self.srs_code)
        approved_srs.progress_status = self.progress_completed
        approved_srs.save(update_fields=["progress_status"])
        for index, code in enumerate([self.itf_code, self.arch_code, self.erd_code, self.db_code, self.ts_code], start=2):
            stale_working = self._create_document(sn=index, version="0.0", document_type=code)
            stale_working.progress_status = self.progress_completed
            stale_working.save(update_fields=["progress_status"])

        response = self.client.get(reverse("doc_generate"), {"docs_cd": "DOC_SRS", "resume": "1"})

        self.assertEqual(response.status_code, 200)
        progress_by_code = {row["code"]: row for row in response.context["progress_rows"]}
        self.assertEqual(progress_by_code["DOC_SRS"]["status"], "confirmed")
        self.assertEqual(progress_by_code["DOC_SRS"]["document_sn"], approved_srs.sn)
        self.assertContains(response, reverse("doc_detail", args=[approved_srs.sn]), html=False)
        self.assertContains(response, "미리보기")
        self.assertEqual(progress_by_code["DOC_ITF"]["status"], "pending")
        self.assertEqual(progress_by_code["DOC_ARCH"]["status"], "pending")
        self.assertFalse(response.context["is_complete"])

    def test_generate_state_hydration_replaces_stale_session_document_with_latest_approved(self):
        initial_erd = self._create_document(sn=137, version="0", document_type=self.erd_code)
        initial_erd.progress_status = self.progress_completed
        initial_erd.save(update_fields=["progress_status"])
        approved_erd = self._create_document(sn=171, version="1.0", document_type=self.erd_code)
        approved_erd.progress_status = self.progress_completed
        approved_erd.save(update_fields=["progress_status"])
        self._set_generation_state(confirmed_documents={"DOC_ERD": initial_erd.sn})

        response = self.client.get(reverse("doc_generate"), {"docs_cd": "DOC_ERD", "resume": "1"})

        self.assertEqual(response.status_code, 200)
        progress_by_code = {row["code"]: row for row in response.context["progress_rows"]}
        self.assertEqual(progress_by_code["DOC_ERD"]["status"], "confirmed")
        self.assertEqual(progress_by_code["DOC_ERD"]["document_sn"], approved_erd.sn)
        self.assertContains(response, reverse("doc_detail", args=[approved_erd.sn]), html=False)

    def test_generate_progress_uses_document_dependency_graph(self):
        initial_srs = self._create_document(sn=1, version="0", document_type=self.srs_code)
        initial_srs.progress_status = self.progress_completed
        initial_srs.save(update_fields=["progress_status"])

        response = self.client.get(reverse("doc_generate"), {"docs_cd": "DOC_ARCH", "resume": "1"})

        self.assertEqual(response.status_code, 200)
        progress_by_code = {row["code"]: row for row in response.context["progress_rows"]}
        self.assertEqual(progress_by_code["DOC_SRS"]["status"], "confirmed")
        self.assertEqual(progress_by_code["DOC_ITF"]["status"], "pending")
        self.assertEqual(progress_by_code["DOC_ARCH"]["status"], "pending")
        self.assertEqual(progress_by_code["DOC_ERD"]["status"], "pending")
        self.assertEqual(progress_by_code["DOC_DB"]["status"], "locked")
        self.assertEqual(progress_by_code["DOC_TS"]["status"], "locked")
        self.assertEqual(progress_by_code["DOC_DB"]["missing_prerequisite_labels"], ["엔티티 관계 모형 설계서"])
        self.assertEqual(progress_by_code["DOC_TS"]["missing_prerequisite_labels"], ["사용자 인터페이스 설계서"])
        self.assertEqual(response.context["selected_document_code"], "DOC_ARCH")
        self.assertTrue(response.context["selected_is_current_step"])

    def test_generate_state_replaces_non_initial_session_document_with_completed_version_zero(self):
        working_srs = self._create_document(sn=10, version="0", document_type=self.srs_code)
        working_srs.progress_status = self.progress_completed
        working_srs.save(update_fields=["progress_status"])
        approved_srs = self._create_document(sn=11, version="1.0", document_type=self.srs_code)
        approved_srs.progress_status = self.progress_completed
        approved_srs.save(update_fields=["progress_status"])
        self._set_generation_state(confirmed_documents={"DOC_SRS": approved_srs.sn})

        response = self.client.get(reverse("doc_generate"), {"docs_cd": "DOC_SRS", "resume": "1"})

        self.assertEqual(response.status_code, 200)
        progress_by_code = {row["code"]: row for row in response.context["progress_rows"]}
        self.assertEqual(progress_by_code["DOC_SRS"]["document_sn"], working_srs.sn)
        self.assertEqual(
            progress_by_code["DOC_SRS"]["detail_url"],
            reverse("doc_detail", args=[working_srs.sn]),
        )
        self.assertEqual(self.client.session["docs_initial_generation"]["confirmed_documents"]["DOC_SRS"], working_srs.sn)

    def test_generate_state_does_not_treat_approved_version_as_initial_completed_document(self):
        approved_srs = self._create_document(sn=12, version="1.0", document_type=self.srs_code)
        approved_srs.progress_status = self.progress_completed
        approved_srs.save(update_fields=["progress_status"])

        response = self.client.get(reverse("doc_generate"), {"docs_cd": "DOC_SRS", "resume": "1"})

        self.assertEqual(response.status_code, 200)
        progress_by_code = {row["code"]: row for row in response.context["progress_rows"]}
        self.assertEqual(progress_by_code["DOC_SRS"]["status"], "pending")
        self.assertNotIn("DOC_SRS", self.client.session["docs_initial_generation"]["confirmed_documents"])

    def test_generate_view_initially_shows_only_file_load_ui(self):
        response = self.client.get(reverse("doc_generate"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["selected_files"])
        self.assertIsNone(response.context["current_draft"])
        self.assertTrue(response.context["show_file_selector"])
        self.assertContains(response, "생성 진행 현황")

    def test_generate_view_job_form_has_explicit_submit_url(self):
        project_file = self._create_project_file()
        self._set_generation_state(selected_file_ids=[project_file.sn])

        response = self.client.get(reverse("doc_generate"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'action="{reverse("doc_generate")}"', html=False)
        self.assertContains(response, f'data-submit-url="{reverse("doc_generate")}"', html=False)
        self.assertContains(response, 'data-doc-job-inline', html=False)
        self.assertContains(response, 'data-doc-job-inline-elapsed-wrap', html=False)
        self.assertNotContains(response, 'data-doc-job-cta-notice', html=False)
        self.assertContains(response, "작업 상태를 확인하고 있습니다.")

    def test_generate_view_shows_regeneration_button_when_saved_flow_is_complete(self):
        confirmed_documents = {}
        for index, code in enumerate(
            [self.srs_code, self.itf_code, self.arch_code, self.erd_code, self.db_code, self.ts_code],
            start=1,
        ):
            document = self._create_document(sn=index, version="0", document_type=code)
            document.progress_status = self.progress_completed
            document.save(update_fields=["progress_status"])
            confirmed_documents[code.code] = document.sn

        self._set_generation_state(confirmed_documents=confirmed_documents)

        response = self.client.get(reverse("doc_generate"), {"docs_cd": "DOC_SRS", "resume": "1"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_complete"])
        self.assertTrue(response.context["can_reset_generation"])
        self.assertContains(response, 'name="action" value="reset_generation"', html=False)

    def test_selecting_files_updates_generation_session_and_redirects_to_clean_url(self):
        project_file = self._create_project_file()

        response = self.client.get(
            reverse("doc_generate"),
            {"selected_files": [project_file.sn], "apply_selection": "1"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{reverse('doc_generate')}?docs_cd=DOC_SRS&resume=1")
        self.assertEqual(
            self.client.session["docs_initial_generation"]["selected_file_ids"],
            [str(project_file.sn)],
        )

    def test_generate_view_restores_active_generation_session_on_plain_entry(self):
        project_file = self._create_project_file()
        self._set_generation_state(selected_file_ids=[project_file.sn])

        response = self.client.get(reverse("doc_generate"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["selected_files"]), 1)
        self.assertTrue(response.context["has_selected_files"])
        self.assertIn("docs_initial_generation", self.client.session)

    def test_generate_view_restores_active_generation_session_for_resume_entry(self):
        project_file = self._create_project_file()
        self._set_generation_state(selected_file_ids=[project_file.sn])

        response = self.client.get(reverse("doc_generate"), {"resume": "1"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["selected_files"]), 1)

    def test_reset_generation_clears_session_state_and_temp_references(self):
        with self.settings(ALPLED_LOCAL_STORAGE_ROOT=self.temp_dir):
            self._create_completed_initial_document(sn=1, document_type=self.srs_code)
            self._set_generation_state(confirmed_documents={"DOC_SRS": 1})
            upload = SimpleUploadedFile("screen.png", b"png-bytes", content_type="image/png")
            self.client.post(
                reverse("doc_generate"),
                {"action": "upload_itf_reference", "docs_cd": "DOC_ITF", "itf_references": [upload]},
            )
            reference_key = self.client.session["docs_initial_generation"]["itf_reference_files"][0]["storage_key"]

            response = self.client.post(
                reverse("doc_generate"),
                {"action": "reset_generation", "docs_cd": "DOC_ITF"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertIn("docs_initial_generation", self.client.session)
        self.assertEqual(self.client.session["docs_initial_generation"]["itf_reference_files"], [])
        self.assertTrue(reference_key.endswith(".png"))

    def test_reset_generation_only_resets_selected_document_type(self):
        completed_documents = {}
        for index, code in enumerate(
            [self.srs_code, self.itf_code, self.arch_code, self.erd_code, self.db_code, self.ts_code],
            start=1,
        ):
            document = self._create_completed_initial_document(sn=index, document_type=code)
            completed_documents[code.code] = document.sn
        self._set_generation_state(confirmed_documents=completed_documents)

        response = self.client.post(
            reverse("doc_generate"),
            {"action": "reset_generation", "docs_cd": "DOC_DB"},
        )
        self.assertEqual(response.status_code, 302)

        follow_up = self.client.get(response["Location"])
        self.assertEqual(follow_up.status_code, 200)
        progress_by_code = {row["code"]: row for row in follow_up.context["progress_rows"]}
        self.assertEqual(progress_by_code["DOC_DB"]["status"], "pending")
        self.assertEqual(progress_by_code["DOC_TS"]["status"], "confirmed")
        self.assertEqual(progress_by_code["DOC_TS"]["document_sn"], completed_documents["DOC_TS"])

    def test_reset_generation_resets_dependency_descendants(self):
        scenarios = [
            ("DOC_SRS", {"DOC_SRS", "DOC_ITF", "DOC_ARCH", "DOC_ERD", "DOC_DB", "DOC_TS"}),
            ("DOC_ITF", {"DOC_ITF", "DOC_TS"}),
            ("DOC_ERD", {"DOC_ERD", "DOC_DB"}),
        ]

        for scenario_index, (target_code, pending_codes) in enumerate(scenarios, start=1):
            with self.subTest(target_code=target_code):
                completed_documents = {}
                sn_base = scenario_index * 100
                for index, code in enumerate(
                    [self.srs_code, self.itf_code, self.arch_code, self.erd_code, self.db_code, self.ts_code],
                    start=sn_base,
                ):
                    document = self._create_completed_initial_document(sn=index, document_type=code)
                    completed_documents[code.code] = document.sn
                self._set_generation_state(confirmed_documents=completed_documents)

                response = self.client.post(
                    reverse("doc_generate"),
                    {"action": "reset_generation", "docs_cd": target_code},
                )
                self.assertEqual(response.status_code, 302)

                follow_up = self.client.get(response["Location"])
                self.assertEqual(follow_up.status_code, 200)
                progress_by_code = {row["code"]: row for row in follow_up.context["progress_rows"]}
                for code in completed_documents:
                    expected_status = "pending" if code in pending_codes else "confirmed"
                    self.assertEqual(progress_by_code[code]["status"], expected_status)

    def test_regeneration_progress_recovers_completed_job_document_for_target(self):
        completed_documents = {}
        for index, code in enumerate(
            [self.srs_code, self.itf_code, self.arch_code, self.erd_code, self.db_code, self.ts_code],
            start=100,
        ):
            document = self._create_completed_initial_document(sn=index, document_type=code)
            completed_documents[code.code] = document.sn
        self._set_generation_state(confirmed_documents=completed_documents)
        old_regenerated_erd = self._create_completed_initial_document(sn=190, document_type=self.erd_code)
        old_regenerated_erd.version = "1.2"
        old_regenerated_erd.save(update_fields=["version"])
        self._create_generation_job(
            sn=190,
            job_id="job-erd-old-completed",
            document=old_regenerated_erd,
            document_type=self.erd_code,
            job_status=self.progress_completed,
        )

        reset_response = self.client.post(
            reverse("doc_generate"),
            {"action": "reset_generation", "docs_cd": "DOC_ERD"},
        )
        self.assertEqual(reset_response.status_code, 302)

        reset_follow_up = self.client.get(reset_response["Location"])
        self.assertEqual(reset_follow_up.status_code, 200)
        reset_progress_by_code = {row["code"]: row for row in reset_follow_up.context["progress_rows"]}
        self.assertEqual(reset_progress_by_code["DOC_ERD"]["status"], "pending")

        regenerated_erd = self._create_completed_initial_document(sn=200, document_type=self.erd_code)
        regenerated_erd.version = "1.3"
        regenerated_erd.save(update_fields=["version"])
        self._create_generation_job(
            sn=200,
            job_id="job-erd-completed",
            document=regenerated_erd,
            document_type=self.erd_code,
            job_status=self.progress_completed,
        )

        response = self.client.get(reset_response["Location"])

        self.assertEqual(response.status_code, 200)
        progress_by_code = {row["code"]: row for row in response.context["progress_rows"]}
        self.assertEqual(progress_by_code["DOC_ERD"]["status"], "confirmed")
        self.assertEqual(progress_by_code["DOC_ERD"]["document_sn"], regenerated_erd.sn)
        self.assertEqual(progress_by_code["DOC_DB"]["status"], "pending")
        self.assertContains(response, reverse("doc_detail", args=[regenerated_erd.sn]), html=False)

    def test_start_current_generation_ajax_returns_job_payload(self):
        project_file = self._create_project_file()
        self._set_generation_state(selected_file_ids=[project_file.sn])
        draft = self._create_document(sn=11, version="0", document_type=self.srs_code)
        job = self._create_generation_job(sn=11, job_id="job-srs-started", document=draft, document_type=self.srs_code)

        with patch(
            "docs.views.start_initial_generation_job",
            return_value={"status": "started", "job": job, "document": draft, "message": "문서 생성을 요청했습니다."},
        ) as start_job_mock:
            response = self.client.post(
                reverse("doc_generate"),
                {"action": "start_current", "selected_files": [project_file.sn]},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "started")
        self.assertEqual(payload["docs_cd"], "DOC_SRS")
        self.assertEqual(payload["job_id"], job.job_id)
        self.assertEqual(payload["started_at"], timezone.localtime(job.started_at).isoformat())
        self.assertGreaterEqual(payload["elapsed_seconds"], 0)
        self.assertIn(reverse("doc_job_status"), payload["poll_url"])
        start_job_mock.assert_called_once()

    def test_doc_generate_replaces_start_button_with_running_notice_for_all_document_types(self):
        sequence = [
            ("DOC_SRS", self.srs_code),
            ("DOC_ITF", self.itf_code),
            ("DOC_ARCH", self.arch_code),
            ("DOC_ERD", self.erd_code),
            ("DOC_DB", self.db_code),
            ("DOC_TS", self.ts_code),
        ]
        for index, (code, document_type) in enumerate(sequence, start=1):
            with self.subTest(code=code):
                self._prepare_generation_state_until(code, sn_offset=index * 1000)
                self._create_generation_job(
                    sn=200 + index,
                    job_id=f"job-{code.lower()}-running-notice",
                    document=None,
                    document_type=document_type,
                    job_status=self.progress_processing,
                )

                response = self.client.get(reverse("doc_generate"), {"docs_cd": code, "resume": 1})

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "문서를 생성 중입니다.")
                self.assertContains(response, "Elapsed")
                self.assertContains(response, 'data-doc-job-inline', html=False)
                self.assertContains(response, 'data-doc-job-inline-elapsed', html=False)
                self.assertNotContains(response, 'data-doc-job-cta-notice', html=False)
                self.assertNotContains(response, 'data-doc-job-cta-root', html=False)
                self.assertContains(response, 'data-doc-job-form', html=False)
                self.assertContains(response, 'class="inline-flex hidden"', html=False)

    def test_doc_generate_hides_elapsed_for_pending_generation_job(self):
        project_file = self._create_project_file()
        self._set_generation_state(selected_file_ids=[project_file.sn])
        self._create_generation_job(
            sn=220,
            job_id="job-srs-pending-notice",
            document=None,
            document_type=self.srs_code,
            job_status=self.progress_pending,
        )

        response = self.client.get(reverse("doc_generate"), {"docs_cd": "DOC_SRS", "resume": 1})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "문서 생성 대기 중입니다.")
        self.assertContains(response, 'data-doc-job-inline-elapsed-wrap class="hidden shrink-0', html=False)
        self.assertContains(response, 'data-doc-job-form', html=False)
        self.assertContains(response, 'class="inline-flex hidden"', html=False)

    def test_doc_generate_restores_start_button_after_failed_generation_job(self):
        project_file = self._create_project_file()
        draft = self._create_document(sn=31, version="0", document_type=self.srs_code)
        self._set_generation_state(
            selected_file_ids=[project_file.sn],
            draft_documents={"DOC_SRS": draft.sn},
        )
        self._create_generation_job(
            sn=31,
            job_id="job-srs-failed-retry",
            document=draft,
            document_type=self.srs_code,
            job_status=self.progress_failed,
        )

        response = self.client.get(reverse("doc_generate"), {"docs_cd": "DOC_SRS", "resume": 1})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_step_code"], "DOC_SRS")
        self.assertIsNone(response.context["current_draft"])
        self.assertTrue(response.context["can_start_current_generation"])
        self.assertContains(response, 'data-doc-job-form', html=False)
        self.assertContains(response, "사용자 요구사항 정의서 생성")
        self.assertNotIn("DOC_SRS", self.client.session["docs_initial_generation"]["draft_documents"])

    def test_confirming_initial_draft_advances_to_next_document_step(self):
        project_file = self._create_project_file()
        draft = self._create_document(sn=1, version="0", document_type=self.srs_code)
        self._create_detail(sn=1, document=draft)
        self._set_generation_state(
            selected_file_ids=[project_file.sn],
            draft_documents={"DOC_SRS": draft.sn},
        )

        response = self.client.post(reverse("doc_confirm", args=[draft.sn]))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("doc_generate")))
        self.assertFalse(Document.objects.filter(document_type=self.srs_code, version="1").exists())
        draft.refresh_from_db()
        self.assertEqual(draft.progress_status_id, "PRGRS_COMPLETED")
        self.assertEqual(draft.modification_content, "저장하기")
        updated_session = self.client.session["docs_initial_generation"]
        self.assertIn("DOC_SRS", updated_session["confirmed_documents"])
        self.assertEqual(updated_session["confirmed_documents"]["DOC_SRS"], draft.sn)
        self.assertNotIn("DOC_SRS", updated_session["draft_documents"])

    def test_itf_start_requires_uploaded_references(self):
        self._create_completed_initial_document(sn=1, document_type=self.srs_code)
        self._set_generation_state(confirmed_documents={"DOC_SRS": 1})

        response = self.client.post(
            reverse("doc_generate"),
            {"action": "start_current", "docs_cd": "DOC_ITF"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Document.objects.filter(document_type=self.itf_code, version="0").count(), 0)
        self.assertTrue(response["Location"].startswith(f"{reverse('doc_generate')}?docs_cd=DOC_ITF&resume=1"))

    def test_itf_upload_accepts_valid_images_and_rejects_invalid_files(self):
        self._create_completed_initial_document(sn=1, document_type=self.srs_code)
        self._set_generation_state(confirmed_documents={"DOC_SRS": 1})
        valid = SimpleUploadedFile("screen.png", b"png-bytes", content_type="image/png")
        invalid = SimpleUploadedFile("notes.txt", b"text", content_type="text/plain")
        oversized = SimpleUploadedFile(
            "large.jpg",
            b"x" * (3 * 1024 * 1024 + 1),
            content_type="image/jpeg",
        )

        with self.settings(ALPLED_LOCAL_STORAGE_ROOT=self.temp_dir):
            response = self.client.post(
                reverse("doc_generate"),
                {
                    "action": "upload_itf_reference",
                    "docs_cd": "DOC_ITF",
                    "itf_references": [valid, invalid, oversized],
                },
            )

        self.assertEqual(response.status_code, 302)
        references = self.client.session["docs_initial_generation"]["itf_reference_files"]
        self.assertEqual(len(references), 1)
        self.assertEqual(references[0]["name"], "screen.png")
        self.assertTrue(references[0]["storage_key"].startswith("temp/"))
        self.assertIn("/temp/", references[0]["path"])
        self.assertTrue((self.temp_dir / references[0]["storage_key"]).exists())

    def test_itf_upload_appends_references_across_multiple_requests(self):
        self._create_completed_initial_document(sn=1, document_type=self.srs_code)
        self._set_generation_state(confirmed_documents={"DOC_SRS": 1})
        first = SimpleUploadedFile("screen-1.png", b"png-bytes-1", content_type="image/png")
        second = SimpleUploadedFile("screen-2.jpg", b"jpg-bytes-2", content_type="image/jpeg")

        with self.settings(ALPLED_LOCAL_STORAGE_ROOT=self.temp_dir):
            first_response = self.client.post(
                reverse("doc_generate"),
                {
                    "action": "upload_itf_reference",
                    "docs_cd": "DOC_ITF",
                    "itf_references": [first],
                },
            )
            second_response = self.client.post(
                reverse("doc_generate"),
                {
                    "action": "upload_itf_reference",
                    "docs_cd": "DOC_ITF",
                    "itf_references": [second],
                },
            )

        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(second_response.status_code, 302)
        references = self.client.session["docs_initial_generation"]["itf_reference_files"]
        self.assertEqual(len(references), 2)
        self.assertEqual([reference["name"] for reference in references], ["screen-1.png", "screen-2.jpg"])
        self.assertTrue(all(reference["storage_key"].startswith("temp/") for reference in references))

    def test_itf_remove_deletes_temp_file_and_session_entry(self):
        self._create_completed_initial_document(sn=1, document_type=self.srs_code)
        self._set_generation_state(confirmed_documents={"DOC_SRS": 1})
        upload = SimpleUploadedFile("screen.png", b"png-bytes", content_type="image/png")

        with self.settings(ALPLED_LOCAL_STORAGE_ROOT=self.temp_dir):
            self.client.post(
                reverse("doc_generate"),
                {"action": "upload_itf_reference", "docs_cd": "DOC_ITF", "itf_references": [upload]},
            )
            reference = self.client.session["docs_initial_generation"]["itf_reference_files"][0]
            self.assertTrue((self.temp_dir / reference["storage_key"]).exists())

            with patch("docs.services.delete_object") as delete_object_mock:
                response = self.client.post(
                    reverse("doc_generate"),
                    {
                        "action": "remove_itf_reference",
                        "docs_cd": "DOC_ITF",
                        "reference_token": reference["token"],
                    },
                )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session["docs_initial_generation"]["itf_reference_files"], [])
        delete_object_mock.assert_called_once_with(reference["storage_key"])
        self.assertTrue(reference["storage_key"].endswith(".png"))

    def test_itf_generation_payload_uses_uploaded_reference_s3_paths(self):
        self._create_completed_initial_document(sn=1, document_type=self.srs_code)
        self._set_generation_state(confirmed_documents={"DOC_SRS": 1})
        upload = SimpleUploadedFile("screen.png", b"png-bytes", content_type="image/png")

        with self.settings(ALPLED_LOCAL_STORAGE_ROOT=self.temp_dir):
            self.client.post(
                reverse("doc_generate"),
                {"action": "upload_itf_reference", "docs_cd": "DOC_ITF", "itf_references": [upload]},
            )
            state = get_generation_state(self.client.session, self.project)
            payload = build_generation_request_payload(self.project, state, "DOC_ITF")

        reference = self.client.session["docs_initial_generation"]["itf_reference_files"][0]
        self.assertEqual(payload["docs_cd"], "DOC_ITF")
        self.assertEqual(payload["image_list"], [reference["path"]])
        self.assertTrue(payload["image_list"][0].startswith("s3://"))
        self.assertIn("/temp/", payload["image_list"][0])

    def test_architecture_form_add_creates_project_net_with_requested_mapping(self):
        self._create_completed_initial_document(sn=1, document_type=self.srs_code)
        self._create_completed_initial_document(sn=2, document_type=self.itf_code)
        self._set_generation_state(confirmed_documents={"DOC_SRS": 1, "DOC_ITF": 2})

        response = self.client.post(
            reverse("doc_generate"),
            {
                "action": "add_project_net",
                "docs_cd": "DOC_ARCH",
                "name": "업무망",
                "purpose": "업무 처리",
                "middleware_stack": "Nginx, Tomcat",
                "firewall_settings": "443 허용",
                "auth_method": "SSO",
                "expected_concurrent_users": "120",
                "cloud_yn": YesNoChoices.YES,
                "hardware_spec": "8core / 32GB",
                "remarks": "이중화 구성",
            },
        )

        self.assertEqual(response.status_code, 302)
        project_net = ProjectNet.objects.get(project=self.project)
        self.assertEqual(project_net.name, "업무망")
        self.assertEqual(project_net.purpose, "업무 처리")
        self.assertEqual(project_net.middleware_stack, "Nginx, Tomcat")
        self.assertEqual(project_net.firewall_settings, "443 허용")
        self.assertEqual(project_net.auth_method, "SSO")
        self.assertEqual(project_net.expected_concurrent_users, 120)
        self.assertEqual(project_net.cloud_yn, YesNoChoices.YES)
        self.assertEqual(project_net.hardware_spec, "8core / 32GB")
        self.assertEqual(project_net.remarks, "이중화 구성")

    def test_architecture_delete_removes_only_target_row_in_current_project(self):
        other_project = Project.objects.create(
            sn=2,
            name="Other Project",
            is_deleted=YesNoChoices.NO,
            created_by=self.user,
            updated_by=self.user,
        )
        target = self._create_project_net(sn=1, name="업무망")
        survivor = self._create_project_net(sn=2, name="외부망", project=other_project)
        self._create_completed_initial_document(sn=1, document_type=self.srs_code)
        self._create_completed_initial_document(sn=3, document_type=self.itf_code)
        self._set_generation_state(confirmed_documents={"DOC_SRS": 1, "DOC_ITF": 3})

        response = self.client.post(
            reverse("doc_generate"),
            {
                "action": "delete_project_net",
                "docs_cd": "DOC_ARCH",
                "project_net_sn": target.sn,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ProjectNet.objects.filter(sn=target.sn, project=self.project).exists())
        self.assertTrue(ProjectNet.objects.filter(sn=survivor.sn, project=other_project).exists())

    def test_architecture_start_requires_project_net_then_returns_job_payload(self):
        self._create_completed_initial_document(sn=1, document_type=self.srs_code)
        self._create_completed_initial_document(sn=2, document_type=self.itf_code)
        self._set_generation_state(confirmed_documents={"DOC_SRS": 1, "DOC_ITF": 2})

        missing_response = self.client.post(
            reverse("doc_generate"),
            {"action": "start_current", "docs_cd": "DOC_ARCH"},
        )

        self.assertEqual(missing_response.status_code, 302)
        self.assertEqual(Document.objects.filter(document_type=self.arch_code, version="0").count(), 0)

        self._create_project_net()
        draft = self._create_document(sn=21, version="0", document_type=self.arch_code)
        job = self._create_generation_job(sn=21, job_id="job-arch-started", document=draft, document_type=self.arch_code)
        with patch(
            "docs.views.start_initial_generation_job",
            return_value={"status": "started", "job": job, "document": draft, "message": "문서 생성을 요청했습니다."},
        ) as start_job_mock:
            success_response = self.client.post(
                reverse("doc_generate"),
                {"action": "start_current", "docs_cd": "DOC_ARCH"},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )

        self.assertEqual(success_response.status_code, 200)
        payload = success_response.json()
        self.assertEqual(payload["status"], "started")
        self.assertEqual(payload["docs_cd"], "DOC_ARCH")
        self.assertEqual(payload["job_id"], job.job_id)
        start_job_mock.assert_called_once()

    def test_architecture_generation_payload_does_not_include_project_net_json(self):
        self._create_completed_initial_document(sn=1, document_type=self.srs_code)
        self._create_completed_initial_document(sn=2, document_type=self.itf_code)
        self._set_generation_state(confirmed_documents={"DOC_SRS": 1, "DOC_ITF": 2})
        self._create_project_net(name="업무망", purpose="내부 시스템")
        state = get_generation_state(self.client.session, self.project)
        payload = build_generation_request_payload(self.project, state, "DOC_ARCH")

        self.assertEqual(payload["docs_cd"], "DOC_ARCH")
        self.assertNotIn("project_nets", payload)
        self.assertEqual(payload["image_list"], [])

    def test_start_initial_generation_job_returns_error_when_fastapi_call_fails(self):
        project_file = self._create_project_file()
        state = {
            "project_sn": self.project.sn,
            "selected_file_ids": [str(project_file.sn)],
            "draft_documents": {},
            "confirmed_documents": {},
            "itf_reference_files": [],
        }

        with patch("docs.services.request_fastapi_generate", side_effect=ValueError("FastAPI base URL is not configured.")):
            result = start_initial_generation_job(self.project, self.user, state)

        self.assertEqual(result["status"], "error")
        self.assertIsNone(result["document"])
        self.assertEqual(result["message"], "FastAPI base URL is not configured.")

    def test_document_auto_apply_ajax_returns_job_payload(self):
        meeting_file = self._create_project_file(sn=30, code=self.file_meeting_code, name="meeting.docx")
        document = self._create_document(sn=31, version="1.0", user=self.user)
        self._create_detail(sn=31, document=document)
        job = self._create_generation_job(
            sn=31,
            job_id="job-auto-apply",
            document=document,
            document_type=self.srs_code,
            job_status=self.progress_pending,
            request_payload={"udt_yn": "Y"},
        )

        with patch(
            "docs.views.start_auto_apply_job",
            return_value={"status": "started", "job": job, "document": document, "message": "회의 내용 자동 적용을 요청했습니다."},
        ) as start_job_mock:
            response = self.client.post(
                reverse("doc_auto_apply", args=[document.sn]),
                {"selected_files": [meeting_file.sn]},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "started")
        self.assertEqual(payload["job_kind"], "auto_apply")
        self.assertEqual(payload["job_id"], job.job_id)
        self.assertIn(reverse("doc_job_status"), payload["poll_url"])
        start_job_mock.assert_called_once()

    def test_document_detail_shows_auto_apply_button_only_for_latest_document(self):
        older_document = self._create_document(sn=50, version="1.0", user=self.user)
        self._create_detail(sn=50, document=older_document)
        latest_document = self._create_document(sn=51, version="1.1", user=self.user)
        self._create_detail(sn=51, document=latest_document)

        older_response = self.client.get(reverse("doc_detail", args=[older_document.sn]), {"mode": "edit"})
        latest_response = self.client.get(reverse("doc_detail", args=[latest_document.sn]), {"mode": "edit"})

        self.assertEqual(older_response.status_code, 200)
        self.assertNotContains(older_response, 'data-modal-target="meeting-files-modal"', html=False)
        self.assertEqual(latest_response.status_code, 200)
        self.assertContains(latest_response, 'data-modal-target="meeting-files-modal"', html=False)

    def test_document_detail_blocks_edit_actions_while_auto_apply_is_running(self):
        document = self._create_document(sn=52, version="1.0", user=self.user)
        self._create_detail(sn=52, document=document)
        self._create_generation_job(
            sn=52,
            job_id="job-auto-apply-running",
            document=document,
            document_type=self.srs_code,
            job_status=self.progress_processing,
            request_payload={"udt_yn": "Y"},
        )

        response = self.client.get(reverse("doc_detail", args=[document.sn]), {"mode": "edit"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["document_change_blocked_by_job"])
        self.assertFalse(response.context["can_auto_apply"])
        self.assertFalse(response.context["can_request_approval"])
        self.assertContains(response, 'data-doc-edit-blocked-by-job="true"', html=False)
        self.assertContains(response, "회의 내용 자동 적용이 진행 중입니다.", html=False)
        self.assertContains(response, "data-doc-save-submit disabled", html=False)
        self.assertNotContains(response, f'{reverse("doc_editor_config", args=[document.sn])}?mode=edit', html=False)

    def test_document_save_is_blocked_while_auto_apply_is_running(self):
        document = self._create_document(sn=53, version="1.0", user=self.user)
        self._create_detail(sn=53, document=document)
        self._create_generation_job(
            sn=53,
            job_id="job-auto-apply-save-block",
            document=document,
            document_type=self.srs_code,
            job_status=self.progress_pending,
            request_payload={"udt_yn": "Y"},
        )

        response = self.client.post(
            reverse("doc_save", args=[document.sn]),
            {"content_text": "자동적용 중 저장 시도"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["message"], "회의 내용 자동 적용이 완료된 뒤 다시 시도해 주세요.")

    def test_document_detail_only_requester_sees_cancel_approval_button(self):
        document = self._create_document(sn=60, version="1.0", user=None)
        detail = self._create_detail(sn=60, document=document)
        approval = DocumentApproval.objects.create(
            approval_sn=60,
            detail=detail,
            approval_status=self.approval_requested,
            request_content="승인 요청입니다.",
            rejection_reason=None,
            created_by=self.user,
            updated_by=self.user,
        )

        requester_response = self.client.get(reverse("doc_detail", args=[document.sn]))
        self.assertEqual(requester_response.status_code, 200)
        self.assertContains(requester_response, reverse("doc_cancel_approval", args=[approval.approval_sn]), html=False)

        self.client.force_login(self.other_user)
        session = self.client.session
        session["current_project_sn"] = self.project.sn
        session.save()
        other_response = self.client.get(reverse("doc_detail", args=[document.sn]))

        self.assertEqual(other_response.status_code, 200)
        self.assertNotContains(other_response, reverse("doc_cancel_approval", args=[approval.approval_sn]), html=False)
        self.assertContains(other_response, "승인 요청 상태 : 승인 대기")

    def test_approval_list_hides_requester_input_for_member(self):
        document = self._create_document(sn=70, version="1.0", user=None)
        detail = self._create_detail(sn=70, document=document)
        DocumentApproval.objects.create(
            approval_sn=70,
            detail=detail,
            approval_status=self.approval_requested,
            request_content="멤버 요청입니다.",
            rejection_reason=None,
            created_by=self.other_user,
            updated_by=self.other_user,
        )

        self.client.force_login(self.other_user)
        session = self.client.session
        session["current_project_sn"] = self.project.sn
        session.save()
        response = self.client.get(reverse("doc_approval_list"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["include_requester_search"])
        self.assertContains(response, 'style="display:none;"', html=False)

    def test_document_job_status_returns_completed_redirect_url(self):
        draft = self._create_document(sn=40, version="0", document_type=self.srs_code)
        job = self._create_generation_job(
            sn=40,
            job_id="job-srs-completed",
            document=draft,
            document_type=self.srs_code,
            job_status=self.progress_completed,
        )

        response = self.client.get(
            reverse("doc_job_status"),
            {
                "job_kind": "initial",
                "docs_cd": "DOC_SRS",
                "job_id": job.job_id,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["redirect_url"], reverse("doc_detail", args=[draft.sn]))

    def test_document_job_status_marks_versioned_completed_document_confirmed_in_session(self):
        document = self._create_document(sn=31, version="1.1", document_type=self.arch_code)
        job = self._create_generation_job(
            sn=31,
            job_id="job-arch-completed",
            document=document,
            document_type=self.arch_code,
            job_status=self.progress_completed,
        )

        response = self.client.get(
            reverse("doc_job_status"),
            {
                "job_kind": "initial",
                "docs_cd": "DOC_ARCH",
                "job_id": job.job_id,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        session_state = self.client.session["docs_initial_generation"]
        self.assertEqual(session_state["confirmed_documents"]["DOC_ARCH"], document.sn)
        self.assertNotIn("DOC_ARCH", session_state["draft_documents"])

    def test_document_job_status_uses_generation_job_started_dt_for_elapsed_time(self):
        started_at = timezone.now() - timedelta(seconds=125)
        job = self._create_generation_job(
            sn=41,
            job_id="job-srs-processing-started-at",
            document_type=self.srs_code,
            job_status=self.progress_processing,
            started_at=started_at,
        )

        response = self.client.get(
            reverse("doc_job_status"),
            {
                "job_kind": "initial",
                "docs_cd": "DOC_SRS",
                "job_id": job.job_id,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["started_at"], timezone.localtime(started_at).isoformat())
        self.assertGreaterEqual(payload["elapsed_seconds"], 120)
        self.assertLess(payload["elapsed_seconds"], 180)

    def test_document_job_status_reinterprets_future_utc_job_timestamp_as_seoul_wallclock(self):
        started_at = timezone.now() + timedelta(hours=8, minutes=55)
        job = self._create_generation_job(
            sn=44,
            job_id="job-srs-processing-kst-wallclock",
            document_type=self.srs_code,
            job_status=self.progress_processing,
            started_at=started_at,
        )

        response = self.client.get(
            reverse("doc_job_status"),
            {
                "job_kind": "initial",
                "docs_cd": "DOC_SRS",
                "job_id": job.job_id,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "running")
        self.assertGreaterEqual(payload["elapsed_seconds"], 240)
        self.assertLess(payload["elapsed_seconds"], 360)

    def test_document_job_status_uses_session_snapshot_until_db_job_exists(self):
        self._set_doc_job_snapshot(
            status="running",
            message="문서를 생성 중입니다.",
            title="사용자 요구사항 정의서 생성",
            docs_cd="DOC_SRS",
            job_kind="initial",
            job_id="job-snapshot-only",
            request_id="req-snapshot",
            tracking_document_sn=None,
            poll_url=reverse("doc_job_status"),
            poll_interval_ms=10000,
            redirect_url="",
            started_at="2026-06-24T00:23:29+00:00",
            elapsed_seconds=1,
            job_status_code="PRGRS_PENDING",
            job_status_label="생성 대기",
            document_sn=None,
            error_cd="",
            error_msg="",
        )

        response = self.client.get(
            reverse("doc_job_status"),
            {
                "job_kind": "initial",
                "docs_cd": "DOC_SRS",
                "job_id": "job-snapshot-only",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["job_id"], "job-snapshot-only")
        self.assertEqual(payload["job_status_code"], "PRGRS_PENDING")

    def test_document_job_status_uses_pending_message_for_waiting_generation_job(self):
        job = self._create_generation_job(
            sn=42,
            job_id="job-srs-pending-message",
            document_type=self.srs_code,
            job_status=self.progress_pending,
        )

        response = self.client.get(
            reverse("doc_job_status"),
            {
                "job_kind": "initial",
                "docs_cd": "DOC_SRS",
                "job_id": job.job_id,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["job_status_code"], "PRGRS_PENDING")
        self.assertEqual(payload["message"], "문서 생성 대기 중입니다.")

    def test_document_job_status_clears_snapshot_after_completed_job(self):
        self._set_doc_job_snapshot(
            status="running",
            message="문서를 생성 중입니다.",
            title="사용자 요구사항 정의서 생성",
            docs_cd="DOC_SRS",
            job_kind="initial",
            job_id="job-completed-clear",
            request_id="req-completed-clear",
            tracking_document_sn=None,
            poll_url=reverse("doc_job_status"),
            poll_interval_ms=10000,
            redirect_url="",
            started_at="2026-06-24T00:23:29+00:00",
            elapsed_seconds=1,
            job_status_code="PRGRS_PENDING",
            job_status_label="생성 대기",
            document_sn=None,
            error_cd="",
            error_msg="",
        )
        draft = self._create_document(sn=43, version="0", document_type=self.srs_code)
        job = self._create_generation_job(
            sn=43,
            job_id="job-completed-clear",
            document=draft,
            document_type=self.srs_code,
            job_status=self.progress_completed,
        )

        response = self.client.get(
            reverse("doc_job_status"),
            {
                "job_kind": "initial",
                "docs_cd": "DOC_SRS",
                "job_id": job.job_id,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "completed")
        self.assertEqual(self.client.session.get("doc_job_snapshots"), None)

    def test_history_detail_shows_common_document_actions(self):
        document = self._create_document(sn=42, version="1.0", document_type=self.srs_code)
        self._create_detail(sn=42, document=document)

        list_response = self.client.get(reverse("doc_history_list"), {"docs_cd": "all"})
        self.assertContains(list_response, f'{reverse("doc_detail", args=[document.sn])}?from=history', html=False)

        detail_response = self.client.get(reverse("doc_detail", args=[document.sn]), {"from": "history"})

        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, reverse("doc_lock", args=[document.sn]), html=False)
        self.assertContains(detail_response, reverse("doc_request_approval", args=[document.sn]), html=False)

    def test_history_list_exposes_active_job_context_for_running_generation(self):
        draft = self._create_document(sn=41, version="0", document_type=self.srs_code)
        job = self._create_generation_job(
            sn=41,
            job_id="job-srs-running",
            document=draft,
            document_type=self.srs_code,
            job_status=self.progress_processing,
        )

        response = self.client.get(reverse("doc_history_list"), {"docs_cd": "DOC_SRS"})

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context["active_job"])
        self.assertEqual(response.context["active_job"]["job_id"], job.job_id)

    def test_doc_generate_progress_rows_reflect_processing_and_failed_jobs(self):
        processing_job = self._create_generation_job(
            sn=44,
            job_id="job-srs-processing",
            document=None,
            document_type=self.srs_code,
            job_status=self.progress_processing,
        )

        processing_response = self.client.get(reverse("doc_generate"), {"docs_cd": "DOC_SRS", "resume": 1})

        self.assertEqual(processing_response.status_code, 200)
        processing_row = next(
            row for row in processing_response.context["progress_rows"] if row["code"] == processing_job.document_type_id
        )
        self.assertEqual(processing_row["status"], "processing")
        self.assertEqual(processing_row["job_status_code"], "PRGRS_PROCESSING")

        processing_job.job_status = self.progress_failed
        processing_job.save(update_fields=["job_status"])

        failed_response = self.client.get(reverse("doc_generate"), {"docs_cd": "DOC_SRS", "resume": 1})

        self.assertEqual(failed_response.status_code, 200)
        failed_row = next(row for row in failed_response.context["progress_rows"] if row["code"] == "DOC_SRS")
        self.assertEqual(failed_row["status"], "failed")
        self.assertEqual(failed_row["job_status_code"], "PRGRS_FAILED")

    def test_history_list_prepends_generation_job_row_when_only_job_exists(self):
        self._create_generation_job(
            sn=52,
            job_id="job-only-running",
            document=None,
            document_type=self.srs_code,
            job_status=self.progress_processing,
        )

        response = self.client.get(reverse("doc_history_list"), {"docs_cd": "DOC_SRS"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["documents"][0]["row_kind"], "job")
        self.assertContains(response, "job_modal=waiting", html=False)

    def test_document_detail_opens_generation_failed_modal(self):
        document = self._create_document(sn=53, version="1.0", document_type=self.srs_code)
        self._create_detail(sn=53, document=document)
        job = self._create_generation_job(
            sn=53,
            job_id="job-failed-detail",
            document=document,
            document_type=self.srs_code,
            job_status=self.progress_failed,
            error_code="REQUIREMENT_GOLD_GENERATION_FAILED",
            error_message="stack trace",
        )

        response = self.client.get(
            reverse("doc_detail", args=[document.sn]),
            {"modal": "generation-failed", "job_sn": job.sn},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["open_generation_failed_modal"])
        self.assertContains(response, "REQUIREMENT_GOLD_GENERATION_FAILED")
        self.assertContains(response, "stack trace")

    def test_document_save_keeps_lock_and_adds_revision(self):
        document = self._create_document(sn=1, version="0", user=self.user)
        self._create_detail(sn=1, document=document)

        response = self.client.post(
            reverse("doc_save", args=[document.sn]),
            {"content_text": "수정한 문서 본문"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, build_document_detail_url(document, mode="edit"))
        self.assertEqual(DocumentDetail.objects.filter(document=document).count(), 2)
        document.refresh_from_db()
        self.assertEqual(document.possession_user_id, self.user.sn)

    def test_saved_working_document_history_is_visible_after_save(self):
        document = self._create_document(sn=44, version="0", user=self.user)
        self._create_detail(sn=44, document=document)

        self.client.post(
            reverse("doc_save", args=[document.sn]),
            {"content_text": "saved revision text"},
        )

        with patch("docs.views.extract_text_from_docx", return_value="saved revision text"):
            response = self.client.get(reverse("doc_detail", args=[document.sn]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["document_state"], "view")
        self.assertTrue(response.context["can_view_revision_history"])
        self.assertContains(response, 'data-modal-target="history-modal"', html=False)
        self.assertEqual(response.context["history_scope_label"], "같은 산출물 종류의 문서 버전 이력을 확인할 수 있습니다.")
        self.assertEqual(len(response.context["revision_rows"]), 1)
        self.assertEqual(response.context["revision_rows"][0]["sn"], document.sn)
        self.assertEqual(
            response.context["revision_rows"][0]["preview_url"],
            reverse("doc_history_preview", args=[document.sn, 44]),
        )

    def test_edit_mode_revision_history_uses_current_document_details(self):
        document = self._create_document(sn=144, version="0", user=self.user)
        self._create_detail(sn=144, document=document)

        self.client.post(
            reverse("doc_save", args=[document.sn]),
            {"content_text": "saved revision text"},
        )

        with patch("docs.views.extract_text_from_docx", return_value="saved revision text"):
            response = self.client.get(reverse("doc_detail", args=[document.sn]), {"mode": "edit"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["document_state"], "edit")
        self.assertEqual(response.context["history_scope_label"], "현재 수정 중인 문서의 저장 이력을 확인하고 원하는 상세 버전으로 복원할 수 있습니다.")
        self.assertEqual(len(response.context["revision_rows"]), 2)
        self.assertTrue(all(row["can_restore"] for row in response.context["revision_rows"]))

    def test_current_editor_reenters_document_in_edit_mode_without_query_param(self):
        document = self._create_document(sn=145, version="1.0", user=self.user)
        self._create_detail(sn=145, document=document)

        with patch("docs.views.extract_text_from_docx", return_value="current editor text"):
            response = self.client.get(reverse("doc_detail", args=[document.sn]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["document_state"], "edit")

    def test_pending_approval_working_document_history_is_visible(self):
        document = self._create_document(sn=45, version="0", user=None)
        detail = self._create_detail(sn=45, document=document)
        DocumentApproval.objects.create(
            approval_sn=45,
            detail=detail,
            approval_status=self.approval_requested,
            request_content="please approve",
            rejection_reason=None,
            created_by=self.user,
            updated_by=self.user,
        )

        with patch("docs.views.extract_text_from_docx", return_value="pending revision text"):
            response = self.client.get(reverse("doc_detail", args=[document.sn]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["document_state"], "waiting")
        self.assertTrue(response.context["can_view_revision_history"])
        self.assertContains(response, 'data-modal-target="history-modal"', html=False)

    def test_document_locked_by_other_user_is_readonly_and_cannot_be_saved(self):
        document = self._create_document(sn=43, version="1.0", user=self.user)
        self._create_detail(sn=43, document=document)
        self.client.force_login(self.other_user)
        session = self.client.session
        session["current_project_sn"] = self.project.sn
        session.save()

        detail_response = self.client.get(reverse("doc_detail", args=[document.sn]))

        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.context["document_state"], "readonly")
        self.assertContains(detail_response, reverse("doc_lock", args=[document.sn]), html=False)

        save_response = self.client.post(
            reverse("doc_save", args=[document.sn]),
            {"content_text": "other user edit"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(save_response.status_code, 403)
        document.refresh_from_db()
        self.assertEqual(document.possession_user_id, self.user.sn)

        lock_response = self.client.post(reverse("doc_lock", args=[document.sn]), follow=True)
        self.assertContains(lock_response, "다른 사용자가 수정중입니다.", html=False)

    def test_document_save_waits_for_onlyoffice_revision_when_form_has_no_text(self):
        document = self._create_document(sn=1, version="1.0", user=self.user)
        detail = self._create_detail(sn=1, document=document)

        with patch("docs.views.request_force_save", return_value={"error": 0}) as force_save_mock, patch(
            "docs.views.wait_for_new_revision", return_value=detail
        ) as wait_mock, patch(
            "docs.views.settings.ONLYOFFICE_DOCUMENT_SERVER_URL",
            "http://document-server",
        ):
            response = self.client.post(reverse("doc_save", args=[document.sn]), {})

        self.assertEqual(response.status_code, 302)
        force_save_mock.assert_called_once()
        wait_mock.assert_called_once_with(document, baseline_detail_sn=detail.sn)

    def test_document_save_ajax_returns_redirect_after_onlyoffice_revision_is_ready(self):
        document = self._create_document(sn=1, version="1.0", user=self.user)
        detail = self._create_detail(sn=1, document=document)
        new_detail = self._create_detail(sn=2, document=document)

        with patch("docs.views.request_force_save", return_value={"error": 0}) as force_save_mock, patch(
            "docs.views.wait_for_new_revision", return_value=new_detail
        ) as wait_mock, patch(
            "docs.views.settings.ONLYOFFICE_DOCUMENT_SERVER_URL",
            "http://document-server",
        ):
            response = self.client.post(
                reverse("doc_save", args=[document.sn]),
                {"baseline_detail_sn": str(detail.sn)},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["redirect_url"], build_document_detail_url(document, mode="edit"))
        force_save_mock.assert_called_once()
        wait_mock.assert_called_once_with(document, baseline_detail_sn=detail.sn)

    def test_document_save_ajax_keeps_edit_mode_when_onlyoffice_revision_is_missing(self):
        document = self._create_document(sn=1, version="1.0", user=self.user)
        detail = self._create_detail(sn=1, document=document)

        with patch("docs.views.request_force_save", return_value={"error": 0}), patch(
            "docs.views.wait_for_new_revision", return_value=detail
        ), patch(
            "docs.views.settings.ONLYOFFICE_DOCUMENT_SERVER_URL",
            "http://document-server",
        ):
            response = self.client.post(
                reverse("doc_save", args=[document.sn]),
                {"baseline_detail_sn": str(detail.sn)},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )

        self.assertEqual(response.status_code, 409)
        document.refresh_from_db()
        self.assertEqual(document.possession_user_id, self.user.sn)

    def test_document_save_ajax_redirects_when_onlyoffice_reports_no_changes(self):
        document = self._create_document(sn=1, version="1.0", user=self.user)
        detail = self._create_detail(sn=1, document=document)

        with patch("docs.views.request_force_save", return_value={"error": 4}) as force_save_mock, patch(
            "docs.views.settings.ONLYOFFICE_DOCUMENT_SERVER_URL",
            "http://document-server",
        ):
            response = self.client.post(
                reverse("doc_save", args=[document.sn]),
                {"baseline_detail_sn": str(detail.sn)},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["redirect_url"], build_document_detail_url(document, mode="edit"))
        self.assertEqual(response.json()["latest_detail_sn"], detail.sn)
        force_save_mock.assert_called_once()

    def test_document_download_uses_shared_document_title_helper(self):
        document = self._create_document(sn=1, version="1.0", user=None)
        self._create_detail(sn=1, document=document, content=b"docx-binary")

        response = self.client.get(f"{reverse('doc_content', args=[document.sn])}?download=1")

        self.assertEqual(response.status_code, 200)
        self.assertIn('filename="DOC_SRS_v1.0.docx"', response["Content-Disposition"])

    def test_document_download_rejects_legacy_detail_without_docs_path(self):
        document = self._create_document(sn=1, version="1.0", user=None)
        DocumentDetail.objects.create(
            sn=1,
            document=document,
            path="legacy.docx",
            is_deleted="N",
            created_by=self.user,
        )

        response = self.client.get(f"{reverse('doc_content', args=[document.sn])}?download=1")

        self.assertEqual(response.status_code, 409)

    def test_history_preview_link_uses_modal_preview_endpoint(self):
        document = self._create_document(sn=1, version="1.0", user=self.user)
        self._create_detail(sn=1, document=document, content=b"seed")

        response = self.client.get(reverse("doc_detail", args=[document.sn]), {"mode": "edit"})

        self.assertEqual(response.status_code, 200)
        preview_url = response.context["revision_rows"][0]["preview_url"]
        self.assertEqual(preview_url, reverse("doc_history_preview", args=[document.sn, 1]))

    def test_history_preview_endpoint_returns_revision_text_without_page_reload(self):
        document = self._create_document(sn=1, version="1.0", user=self.user)
        detail = self._create_detail(sn=1, document=document, content=b"seed")

        with patch("docs.views.extract_text_from_docx", return_value="미리보기 본문"):
            response = self.client.get(reverse("doc_history_preview", args=[document.sn, detail.sn]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["preview_text"], "미리보기 본문")

    def test_history_preview_endpoint_returns_404_for_missing_revision(self):
        document = self._create_document(sn=1, version="1.0", user=self.user)
        self._create_detail(sn=1, document=document, content=b"seed")

        response = self.client.get(reverse("doc_history_preview", args=[document.sn, 999]))

        self.assertEqual(response.status_code, 404)

    def test_document_callback_saves_onlyoffice_revision(self):
        document = self._create_document(sn=1, version="0", user=None)
        self._create_detail(sn=1, document=document, content=b"seed")

        with patch("docs.views.download_remote_content", return_value=b"OnlyOffice save"):
            response = self.client.post(
                f"{reverse('doc_callback', args=[document.sn])}?baseline_detail_sn=1",
                data='{"status": 2, "url": "http://document-server/edited.docx"}',
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(DocumentDetail.objects.filter(document=document).count(), 2)

    def test_document_callback_skips_revision_when_onlyoffice_content_is_unchanged(self):
        document = self._create_document(sn=1, version="0", user=None)
        self._create_detail(sn=1, document=document, content=b"seed")

        with patch("docs.views.download_remote_content", return_value=b"seed"):
            response = self.client.post(
                f"{reverse('doc_callback', args=[document.sn])}?baseline_detail_sn=1",
                data='{"status": 2, "url": "http://document-server/unchanged.docx"}',
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(DocumentDetail.objects.filter(document=document).count(), 1)

    def test_editor_config_uses_desktop_type_for_edit_mode(self):
        document = self._create_document(sn=1, version="1.0", user=self.user)
        self._create_detail(sn=1, document=document, content=b"seed")

        response = self.client.get(reverse("doc_editor_config", args=[document.sn]), {"mode": "edit"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["type"], "desktop")
        self.assertEqual(payload["editorConfig"]["mode"], "edit")
        self.assertTrue(payload["document"]["permissions"]["edit"])

    def test_editor_config_uses_embedded_type_for_view_mode(self):
        document = self._create_document(sn=1, version="1.0", user=None)
        self._create_detail(sn=1, document=document, content=b"seed")

        response = self.client.get(reverse("doc_editor_config", args=[document.sn]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["type"], "embedded")
        self.assertEqual(payload["editorConfig"]["mode"], "view")
        self.assertFalse(payload["document"]["permissions"]["edit"])

    def test_document_detail_uses_relative_onlyoffice_url_for_browser(self):
        document = self._create_document(sn=1, version="1.0", user=None)
        self._create_detail(sn=1, document=document, content=b"seed")

        with patch(
            "docs.views.settings.ONLYOFFICE_DOCUMENT_SERVER_URL",
            "http://43.203.176.226:8888/web-apps/apps/api/documents/api.js",
        ):
            response = self.client.get(reverse("doc_detail", args=[document.sn]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-document-server-url="/onlyoffice"', html=False)

    def test_editor_config_uses_request_host_instead_of_internal_public_base_url(self):
        document = self._create_document(sn=1, version="1.0", user=None)
        self._create_detail(sn=1, document=document, content=b"seed")

        with patch(
            "docs.services.settings.DJANGO_PUBLIC_BASE_URL",
            "http://host.docker.internal:8000",
        ):
            response = self.client.get(reverse("doc_editor_config", args=[document.sn]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["document"]["url"].startswith("http://testserver/docs/documents/"))
        self.assertTrue(payload["editorConfig"]["callbackUrl"].startswith("http://testserver/docs/documents/"))

    def test_onlyoffice_browser_url_normalizes_full_api_js_path(self):
        with self.settings(
            ONLYOFFICE_DOCUMENT_SERVER_URL="http://43.203.176.226:8888/web-apps/apps/api/documents/api.js"
        ):
            browser_url = get_onlyoffice_document_server_url(browser=True)

        self.assertEqual(browser_url, "/onlyoffice")

    def test_approval_list_view_renders_with_db_driven_choices(self):
        document = self._create_document(sn=1, version="1.0", user=None)
        detail = self._create_detail(sn=1, document=document)
        DocumentApproval.objects.create(
            approval_sn=1,
            detail=detail,
            approval_status=self.approval_requested,
            request_content="승인 요청입니다.",
            rejection_reason=None,
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.get(reverse("doc_approval_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["document_type_choices"][1][0], "DOC_SRS")

    def test_document_detail_hides_approval_request_button_in_view_mode(self):
        document = self._create_document(sn=1, version="1.0", user=None)
        self._create_detail(sn=1, document=document)

        response = self.client.get(reverse("doc_detail", args=[document.sn]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["can_request_approval"])
        self.assertNotContains(response, 'data-modal-target="approval-request-modal"', html=False)
        self.assertNotContains(response, 'textarea name="request_content"', html=False)

    def test_document_detail_shows_approval_request_button_in_edit_mode(self):
        document = self._create_document(sn=1, version="1.0", user=self.user)
        self._create_detail(sn=1, document=document)

        response = self.client.get(reverse("doc_detail", args=[document.sn]), {"mode": "edit"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["can_request_approval"])
        self.assertContains(response, 'data-modal-target="approval-request-modal"', html=False)
        self.assertContains(response, 'textarea name="request_content"', html=False)
        self.assertContains(response, 'maxlength="100"', html=False)

    def test_generation_draft_detail_hides_approval_request_button_in_view_mode(self):
        document = self._create_document(sn=46, version="0", document_type=self.srs_code, user=None)
        self._create_detail(sn=46, document=document)
        self._set_generation_state(draft_documents={"DOC_SRS": document.sn})

        response = self.client.get(reverse("doc_detail", args=[document.sn]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_generation_draft"])
        self.assertFalse(response.context["can_request_approval"])
        self.assertNotContains(response, 'data-modal-target="approval-request-modal"', html=False)

    def test_working_document_from_history_url_still_shows_edit_button_without_approval_button(self):
        document = self._create_document(sn=48, version="0", document_type=self.srs_code, user=None)
        self._create_detail(sn=48, document=document)
        self._set_generation_state(draft_documents={"DOC_SRS": document.sn})

        response = self.client.get(reverse("doc_detail", args=[document.sn]), {"from": "history"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["can_edit"])
        self.assertFalse(response.context["can_request_approval"])
        self.assertContains(response, reverse("doc_lock", args=[document.sn]), html=False)
        self.assertNotContains(response, 'data-modal-target="approval-request-modal"', html=False)

    def test_locked_generation_draft_hides_save_and_edit_actions(self):
        ProjectUserRole.objects.filter(project=self.project, user=self.other_user).update(role=self.role_manager)
        document = self._create_document(sn=49, version="0", document_type=self.itf_code, user=self.user)
        self._create_detail(sn=49, document=document)
        self._set_generation_state(draft_documents={"DOC_ITF": document.sn}, confirmed_documents={"DOC_SRS": 1})
        self.client.force_login(self.other_user)
        session = self.client.session
        session["current_project_sn"] = self.project.sn
        session["docs_initial_generation"] = {
            "project_sn": self.project.sn,
            "selected_file_ids": [],
            "draft_documents": {"DOC_ITF": document.sn},
            "confirmed_documents": {"DOC_SRS": 1},
            "itf_reference_files": [],
        }
        session.save()

        response = self.client.get(reverse("doc_detail", args=[document.sn]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["document_state"], "readonly")
        self.assertTrue(response.context["can_edit"])
        self.assertFalse(response.context["can_confirm"])
        self.assertContains(response, reverse("doc_lock", args=[document.sn]), html=False)
        self.assertNotContains(response, reverse("doc_confirm", args=[document.sn]), html=False)

        lock_response = self.client.post(reverse("doc_lock", args=[document.sn]), follow=True)
        self.assertContains(lock_response, "다른 사용자가 수정중입니다.", html=False)

        approval_response = self.client.post(
            reverse("doc_request_approval", args=[document.sn]),
            {"request_content": "please approve"},
            follow=True,
        )
        self.assertContains(
            approval_response,
            "다른 사용자가 수정중입니다. 승인요청은 수정 후 저장한 뒤 가능합니다.",
            html=False,
        )

    def test_generation_draft_save_action_is_rendered_below_document_viewer(self):
        document = self._create_document(sn=50, version="0", document_type=self.srs_code, user=None)
        self._create_detail(sn=50, document=document)
        self._set_generation_state(draft_documents={"DOC_SRS": document.sn})

        response = self.client.get(reverse("doc_detail", args=[document.sn]))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        viewer_index = html.index("data-onlyoffice-root")
        save_index = html.index(reverse("doc_confirm", args=[document.sn]))
        self.assertGreater(save_index, viewer_index)

    def test_document_request_approval_allows_last_editor_from_detail_view(self):
        document = self._create_document(sn=1, version="1.0", user=None)
        detail = self._create_detail(sn=1, document=document)

        with patch("docs.views.request_fastapi_approval_review", return_value={"status": "accepted"}) as review_mock:
            response = self.client.post(
                reverse("doc_request_approval", args=[document.sn]),
                {"request_content": "승인 요청입니다."},
            )

        self.assertEqual(response.status_code, 302)
        approval = DocumentApproval.objects.get(detail=detail)
        self.assertEqual(approval.request_content, "승인 요청입니다.")
        review_mock.assert_called_once_with(approval.approval_sn)

    def test_document_request_approval_rejects_content_longer_than_100_chars(self):
        document = self._create_document(sn=51, version="1.0", user=None)
        detail = self._create_detail(sn=51, document=document)
        request_content = "가" * 101

        with patch("docs.views.request_fastapi_approval_review") as review_mock:
            response = self.client.post(
                reverse("doc_request_approval", args=[document.sn]),
                {"request_content": request_content},
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "승인 요청 내용은 100자 이하로 입력해 주세요.", html=False)
        self.assertTrue(response.context["open_approval_request_modal"])
        self.assertFalse(DocumentApproval.objects.filter(detail=detail).exists())
        review_mock.assert_not_called()

    def test_document_request_approval_allows_current_editor_and_releases_lock(self):
        document = self._create_document(sn=11, version="1.0", user=self.user)
        detail = self._create_detail(sn=11, document=document)

        with patch("docs.views.request_fastapi_approval_review", return_value={"status": "accepted"}) as review_mock:
            response = self.client.post(
                reverse("doc_request_approval", args=[document.sn]),
                {"request_content": "수정 완료 승인 요청"},
            )

        self.assertEqual(response.status_code, 302)
        approval = DocumentApproval.objects.get(detail=detail)
        self.assertEqual(approval.request_content, "수정 완료 승인 요청")
        document.refresh_from_db()
        self.assertIsNone(document.possession_user)
        review_mock.assert_called_once_with(approval.approval_sn)

    def test_generation_draft_request_approval_allows_last_editor(self):
        document = self._create_document(sn=47, version="0", document_type=self.srs_code, user=None)
        detail = self._create_detail(sn=47, document=document)
        self._set_generation_state(draft_documents={"DOC_SRS": document.sn})

        response = self.client.post(
            reverse("doc_request_approval", args=[document.sn]),
            {"request_content": "draft approval request"},
        )

        self.assertEqual(response.status_code, 302)
        approval = DocumentApproval.objects.get(detail=detail)
        self.assertEqual(approval.request_content, "draft approval request")

    def test_approval_detail_uses_modal_buttons_instead_of_inline_forms(self):
        document = self._create_document(sn=1, version="1.0", user=None)
        detail = self._create_detail(sn=1, document=document)
        approval = DocumentApproval.objects.create(
            approval_sn=1,
            detail=detail,
            approval_status=self.approval_requested,
            request_content="승인 요청입니다.",
            rejection_reason=None,
            created_by=self.user,
            updated_by=self.user,
        )

        review_job = SimpleNamespace(
            status_code="SUCCEEDED",
            before_data={"tables": []},
            after_data={"tables": []},
            result={"change_review": {"changes": [], "summary": {}}},
            before_detail_id=None,
            after_detail_id=None,
        )
        with patch("docs.views.get_latest_approval_review_job", return_value=review_job):
            response = self.client.get(reverse("doc_approval_detail", args=[approval.approval_sn]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-modal-target="approval-approve-modal"', html=False)
        self.assertContains(response, 'data-modal-target="approval-reject-modal"', html=False)
        self.assertNotContains(response, "정합성 자동검토")

    def test_approval_detail_shows_pending_review_message(self):
        document = self._create_document(sn=80, version="1.0", user=None)
        detail = self._create_detail(sn=80, document=document)
        approval = DocumentApproval.objects.create(
            approval_sn=80,
            detail=detail,
            approval_status=self.approval_requested,
            request_content="검토 대기 요청",
            created_by=self.user,
            updated_by=self.user,
        )

        review_job = SimpleNamespace(status_code="PROCESSING")
        with patch("docs.views.get_latest_approval_review_job", return_value=review_job):
            response = self.client.get(reverse("doc_approval_detail", args=[approval.approval_sn]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "변경 이력과 정합성을 확인하고 있습니다.")
        self.assertContains(response, "data-approval-review-pending", html=False)
        self.assertNotContains(response, 'data-modal-target="approval-approve-modal"', html=False)

    def test_approval_detail_renders_review_json(self):
        document = self._create_document(sn=81, version="1.0", user=None)
        detail = self._create_detail(sn=81, document=document)
        approval = DocumentApproval.objects.create(
            approval_sn=81,
            detail=detail,
            approval_status=self.approval_requested,
            request_content="JSON 검토 요청",
            created_by=self.user,
            updated_by=self.user,
        )
        review_job = SimpleNamespace(
            status_code="SUCCEEDED",
            before_detail_id=detail.sn,
            after_detail_id=detail.sn,
            before_data={
                "tables": [
                    {
                        "table_id": "tbl_user",
                        "table_name": "사용자",
                        "columns": [{"column_id": "user_sn", "logical_name": "사용자 일련번호"}],
                    }
                ]
            },
            after_data={"tables": []},
            result={
                "change_review": {
                    "summary": {"added_count": 1, "deleted_count": 0, "modified_count": 0},
                    "changes": [
                        {
                            "title": "user_name",
                            "change_type": "added",
                            "message": "사용자명 컬럼이 추가되었습니다.",
                            "affected_artifacts": ["TS"],
                        }
                    ],
                },
                "consistency_check": {
                    "summary": {"matched_count": 0, "missing_count": 1, "conflict_count": 0},
                    "messages": [{"type": "missing", "requirement_id": "SFR-001", "text": "요구사항이 누락되었습니다."}],
                },
            },
        )

        with patch("docs.views.get_latest_approval_review_job", return_value=review_job):
            response = self.client.get(reverse("doc_approval_detail", args=[approval.approval_sn]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "tbl_user")
        self.assertContains(response, "사용자명 컬럼이 추가되었습니다.")
        self.assertNotContains(response, "요구사항 정합성")
        self.assertContains(response, "변경 전")
        self.assertContains(response, "변경 후")
        self.assertContains(response, "전체 원본 데이터 보기")

    def test_approval_detail_shows_no_changes_message(self):
        document = self._create_document(sn=82, version="1.0", user=None)
        detail = self._create_detail(sn=82, document=document)
        approval = DocumentApproval.objects.create(
            approval_sn=82,
            detail=detail,
            approval_status=self.approval_requested,
            request_content="동일 데이터 요청",
            created_by=self.user,
            updated_by=self.user,
        )
        review_job = SimpleNamespace(
            status_code="SUCCEEDED",
            before_detail_id=None,
            after_detail_id=None,
            before_data={"requirements": [{"requirement_id": "SFR-001"}]},
            after_data={"requirements": [{"requirement_id": "SFR-001"}]},
            result={
                "change_review": {
                    "summary": {"added_count": 0, "deleted_count": 0, "modified_count": 0},
                    "changes": [],
                },
                "consistency_check": {
                    "summary": {"matched_count": 1, "missing_count": 0, "conflict_count": 0},
                    "messages": [],
                },
            },
        )

        with patch("docs.views.get_latest_approval_review_job", return_value=review_job):
            response = self.client.get(reverse("doc_approval_detail", args=[approval.approval_sn]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "변경된 항목이 없습니다.")
        self.assertContains(response, "변경 전후 데이터가 동일합니다.")

    def test_manager_cannot_approve_duplicate_version_for_same_document_type(self):
        document = self._create_document(sn=1, version="1.0", user=None)
        detail = self._create_detail(sn=1, document=document)
        approval = DocumentApproval.objects.create(
            approval_sn=1,
            detail=detail,
            approval_status=self.approval_requested,
            request_content="승인 요청입니다.",
            rejection_reason=None,
            created_by=self.user,
            updated_by=self.user,
        )
        self._create_document(sn=2, version="1.1", user=None, document_type=self.srs_code)

        response = self.client.post(
            reverse("doc_approval_approve", args=[approval.approval_sn]),
            {"new_version": "1.1"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith("?modal=approve"))
        approval.refresh_from_db()
        self.assertEqual(approval.approval_status_id, "APRV_REQ")

    def test_manager_can_approve_request_and_create_new_version(self):
        document = self._create_document(sn=1, version="1.0", user=None)
        detail = self._create_detail(sn=1, document=document)
        approval = DocumentApproval.objects.create(
            approval_sn=1,
            detail=detail,
            approval_status=self.approval_requested,
            request_content="승인 요청입니다.",
            rejection_reason=None,
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.post(
            reverse("doc_approval_approve", args=[approval.approval_sn]),
            {"new_version": "1.1"},
        )

        self.assertEqual(response.status_code, 302)
        approval.refresh_from_db()
        self.assertEqual(approval.approval_status_id, "APRV_COM")
        approved_document = Document.objects.get(version="1.1")
        self.assertEqual(response.url, reverse("doc_detail", args=[approved_document.sn]))

        detail_response = self.client.get(response.url)

        self.assertTrue(detail_response.context["can_edit"])
        self.assertContains(detail_response, reverse("doc_lock", args=[approved_document.sn]), html=False)
