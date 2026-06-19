import tempfile
import unittest
from pathlib import Path
from typing import Any

from config.settings import Settings
from tools.result import error_result, success_result
from workflow.nodes.export_node import ExportDependencies, export_node


class FileRepositoryStub:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def insert_file(self, **kwargs: Any) -> dict[str, int]:
        self.calls.append(kwargs)
        return {"file_sn": 123}


class DocsDetailRepositoryStub:
    def __init__(self) -> None:
        self.deactivated: list[tuple[int, str]] = []
        self.inserted: list[dict[str, Any]] = []
        self.done: list[tuple[int, str]] = []
        self.failed: list[tuple[int, str, str]] = []

    def deactivate_active_doc(self, project_sn: int, docs_cd: str) -> None:
        self.deactivated.append((project_sn, docs_cd))

    def insert_docs_detail(self, **kwargs: Any) -> None:
        self.inserted.append(kwargs)

    def update_docs_status_done(self, project_sn: int, docs_cd: str) -> None:
        self.done.append((project_sn, docs_cd))

    def update_docs_status_failed(
        self, project_sn: int, docs_cd: str, error_message: str
    ) -> None:
        self.failed.append((project_sn, docs_cd, error_message))


class ProjectRepositoryStub:
    def __init__(self, project: dict[str, Any] | None = None) -> None:
        self.project = project or {"prj_nm": "테스트 시스템"}

    def find_project_by_sn(self, project_sn: int) -> dict[str, Any] | None:
        return self.project


class DocsRepositoryStub:
    def __init__(self, docs: dict[str, Any] | None = None) -> None:
        self.docs = docs or {"docs_ver": "2.5"}

    def find_project_docs_by_code(
        self,
        project_sn: int,
        docs_cd: str,
    ) -> dict[str, Any] | None:
        return self.docs


def exporter_stub(payload: dict[str, Any], output_path: str, **_: Any):
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"docx")
    return success_result(
        {"local_file_path": str(target), "file_name": target.name, "file_size": 4}
    )


def exporter_different_path_stub(payload: dict[str, Any], output_path: str, **_: Any):
    target = Path(output_path).with_name("custom_export.docx")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"custom")
    return success_result(
        {"local_file_path": str(target), "file_name": target.name, "file_size": 6}
    )


def uploader_stub(local_file_path: str, **_: Any):
    return success_result({"storage_file_path": f"s3://bucket/{Path(local_file_path).name}"})


class ExportNodeTest(unittest.TestCase):
    def dependencies(
        self, root: str, *, uploader=uploader_stub
    ) -> tuple[ExportDependencies, FileRepositoryStub, DocsDetailRepositoryStub]:
        file_repository = FileRepositoryStub()
        docs_repository = DocsDetailRepositoryStub()
        settings = Settings(_env_file=None, output_dir=Path(root), s3_bucket="bucket")
        return (
            ExportDependencies(
                file_repository=file_repository,
                docs_detail_repository=docs_repository,
                docx_exporter=exporter_stub,
                uploader=uploader,
                settings=settings,
            ),
            file_repository,
            docs_repository,
        )

    def test_srs_create_registers_only_final_json_file_and_marks_done(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            dependencies, files, docs = self.dependencies(root)
            state = {
                "project_sn": 10,
                "docs_cd": "SRS",
                "udt_yn": "N",
                "final_document_json": {
                    "docs_cd": "SRS",
                    "requirement_json_list": [],
                },
                "errors": [],
            }

            result = export_node(state, dependencies)

            self.assertEqual(result["status"], "DONE")
            self.assertIsNone(result["export_result"]["file_sn"])
            self.assertEqual(result["export_result"]["requirement_json_file_sn"], 123)
            self.assertEqual(files.calls[0]["file_ext"], "json")
            self.assertEqual(files.calls[0]["file_cd"], "FILE_REQ_DOC_JSON")
            self.assertEqual(files.calls[0]["project_sn"], 10)
            self.assertEqual(len(files.calls), 1)
            self.assertIsNone(docs.inserted[0]["file_sn"])
            self.assertEqual(docs.done, [(10, "SRS")])
            self.assertFalse(docs.deactivated)

    def test_exports_all_document_types_with_required_final_json_shapes(self) -> None:
        cases = {
            "SRS": {"docs_cd": "SRS", "requirement_json_list": []},
            "INTERFACE": {"docs_cd": "INTERFACE", "interface_json_list": [], "ui_structure": []},
            "TS": {"docs_cd": "TS", "integrated_test_scenario_json": {}},
            "ERD": {"docs_cd": "ERD", "erd_entity_json": {}, "mermaid_image_path": ""},
            "DB": {"docs_cd": "DB", "db_design_json": {}},
            "ARCH": {"docs_cd": "ARCH", "architecture_document_json": {}, "mermaid_image_path": ""},
        }
        for docs_cd, final_document_json in cases.items():
            with self.subTest(docs_cd=docs_cd), tempfile.TemporaryDirectory() as root:
                dependencies, files, docs = self.dependencies(root)
                result = export_node(
                    {
                        "project_sn": 10,
                        "docs_cd": docs_cd,
                        "udt_yn": "N",
                        "final_document_json": final_document_json,
                    },
                    dependencies,
                )

                self.assertEqual(result["status"], "DONE")
                self.assertEqual(result["export_result"]["docs_cd"], docs_cd)
                if docs_cd == "SRS":
                    self.assertEqual(len(files.calls), 1)
                    self.assertEqual(files.calls[0]["file_ext"], "json")
                    self.assertEqual(files.calls[0]["file_cd"], "FILE_REQ_DOC_JSON")
                else:
                    self.assertEqual(len(files.calls), 0)
                self.assertEqual(docs.inserted[0]["docs_cd"], docs_cd)
                self.assertTrue(docs.inserted[0]["docs_path"].startswith("s3://bucket/"))
                self.assertIsNone(docs.inserted[0]["file_sn"])

    def test_enriches_docx_payload_with_project_name_and_docs_version(self) -> None:
        captured_payloads: list[dict[str, Any]] = []

        def capturing_exporter(payload: dict[str, Any], output_path: str, **_: Any):
            captured_payloads.append(payload)
            return exporter_stub(payload, output_path)

        with tempfile.TemporaryDirectory() as root:
            dependencies, _, _ = self.dependencies(root)
            dependencies = ExportDependencies(
                file_repository=dependencies.file_repository,
                docs_detail_repository=dependencies.docs_detail_repository,
                project_repository=ProjectRepositoryStub({"prj_nm": "ALPLED 통합 플랫폼"}),
                docs_repository=DocsRepositoryStub({"docs_ver": "v2.7"}),
                docx_exporter=capturing_exporter,
                uploader=dependencies.uploader,
                settings=dependencies.settings,
            )
            result = export_node(
                {
                    "project_sn": 10,
                    "docs_cd": "DB",
                    "udt_yn": "N",
                    "final_document_json": {
                        "docs_cd": "DB",
                        "db_design_json": {"tables": []},
                    },
                },
                dependencies,
            )

            self.assertEqual(result["status"], "DONE")
            payload = captured_payloads[0]
            self.assertEqual(payload["metadata"]["system_name"], "ALPLED 통합 플랫폼")
            self.assertEqual(payload["metadata"]["version"], "v2.7")
            self.assertEqual(
                payload["content"]["db_design_json"]["system_name"],
                "ALPLED 통합 플랫폼",
            )
            self.assertEqual(payload["content"]["db_design_json"]["version"], "v2.7")

    def test_update_inserts_new_detail_without_deactivating_previous_version(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            dependencies, _, docs = self.dependencies(root)
            result = export_node(
                {
                    "project_sn": 10,
                    "docs_cd": "DB",
                    "udt_yn": "Y",
                    "final_document_json": {"docs_cd": "DB", "db_design_json": {}},
                },
                dependencies,
            )

            self.assertEqual(result["status"], "DONE")
            self.assertEqual(docs.deactivated, [])
            self.assertEqual(docs.inserted[0]["status"], "DONE")

    def test_uses_actual_exported_file_path_for_upload_and_db_record(self) -> None:
        uploaded_paths = []

        def uploader(local_file_path: str, **_: Any):
            uploaded_paths.append(local_file_path)
            return success_result({"storage_file_path": f"s3://bucket/{Path(local_file_path).name}"})

        with tempfile.TemporaryDirectory() as root:
            dependencies, files, _ = self.dependencies(root, uploader=uploader)
            dependencies = ExportDependencies(
                file_repository=dependencies.file_repository,
                docs_detail_repository=dependencies.docs_detail_repository,
                docx_exporter=exporter_different_path_stub,
                uploader=uploader,
                settings=dependencies.settings,
            )
            result = export_node(
                {
                    "project_sn": 10,
                    "docs_cd": "SRS",
                    "udt_yn": "N",
                    "final_document_json": {"docs_cd": "SRS", "requirement_json_list": []},
                },
                dependencies,
            )

            self.assertEqual(Path(uploaded_paths[-1]).name, "custom_export.docx")
            self.assertEqual(result["export_result"]["file_name"], "custom_export.docx")
            self.assertEqual(len(files.calls), 1)
            self.assertEqual(files.calls[0]["file_ext"], "json")

    def test_srs_create_uploads_requirement_json_before_docx(self) -> None:
        uploaded_paths = []

        def uploader(local_file_path: str, **kwargs: Any):
            uploaded_paths.append((local_file_path, kwargs))
            return success_result({"storage_file_path": f"s3://bucket/{Path(local_file_path).name}"})

        with tempfile.TemporaryDirectory() as root:
            dependencies, files, _ = self.dependencies(root, uploader=uploader)
            result = export_node(
                {
                    "project_sn": 10,
                    "docs_cd": "SRS",
                    "udt_yn": "N",
                    "final_document_json": {
                        "docs_cd": "SRS",
                        "requirement_json_list": [{"requirement_id": "SFR-001"}],
                    },
                },
                dependencies,
            )

            self.assertEqual(result["status"], "DONE")
            self.assertEqual(Path(uploaded_paths[0][0]).suffix, ".json")
            self.assertEqual(Path(uploaded_paths[1][0]).suffix, ".docx")
            self.assertEqual(files.calls[0]["file_cd"], "FILE_REQ_DOC_JSON")
            self.assertEqual(files.calls[0]["file_ext"], "json")
            self.assertEqual(len(files.calls), 1)

    def test_srs_update_also_uploads_replacement_requirement_json(self) -> None:
        uploaded_paths = []

        def uploader(local_file_path: str, **kwargs: Any):
            uploaded_paths.append((local_file_path, kwargs))
            return success_result({"storage_file_path": f"s3://bucket/{Path(local_file_path).name}"})

        with tempfile.TemporaryDirectory() as root:
            dependencies, files, docs = self.dependencies(root, uploader=uploader)
            result = export_node(
                {
                    "project_sn": 10,
                    "docs_cd": "SRS",
                    "udt_yn": "Y",
                    "final_document_json": {
                        "docs_cd": "SRS",
                        "requirement_json_list": [{"requirement_id": "SFR-001"}],
                    },
                },
                dependencies,
            )

            self.assertEqual(result["status"], "DONE")
            self.assertEqual(docs.deactivated, [])
            self.assertEqual(Path(uploaded_paths[0][0]).suffix, ".json")
            self.assertEqual(Path(uploaded_paths[1][0]).suffix, ".docx")
            self.assertEqual(files.calls[0]["file_cd"], "FILE_REQ_DOC_JSON")
            self.assertEqual(len(files.calls), 1)

    def test_failure_marks_export_and_docs_failed(self) -> None:
        def failed_uploader(local_file_path: str, **_: Any):
            return error_result("UPLOAD_FAILED", "업로드 실패")

        with tempfile.TemporaryDirectory() as root:
            dependencies, _, docs = self.dependencies(root, uploader=failed_uploader)
            result = export_node(
                {
                    "project_sn": 10,
                    "docs_cd": "ERD",
                    "udt_yn": "N",
                    "final_document_json": {
                        "docs_cd": "ERD",
                        "erd_entity_json": {},
                        "mermaid_image_path": "",
                    },
                },
                dependencies,
            )

            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(result["export_result"]["status"], "FAILED")
            self.assertEqual(docs.failed[0][0:2], (10, "ERD"))

    def test_missing_final_document_fails_before_export(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            dependencies, _, docs = self.dependencies(root)
            result = export_node(
                {"project_sn": 10, "docs_cd": "ARCH", "udt_yn": "N"},
                dependencies,
            )

            self.assertEqual(result["errors"][0]["code"], "FINAL_DOCUMENT_JSON_MISSING")
            self.assertTrue(docs.failed)


if __name__ == "__main__":
    unittest.main()
