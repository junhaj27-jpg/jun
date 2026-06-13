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


def exporter_stub(payload: dict[str, Any], output_path: str, **_: Any):
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"docx")
    return success_result(
        {"local_file_path": str(target), "file_name": target.name, "file_size": 4}
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

    def test_create_exports_registers_file_and_marks_done(self) -> None:
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
            self.assertEqual(result["export_result"]["file_sn"], 123)
            self.assertEqual(files.calls[0]["file_extn"], "docx")
            self.assertEqual(docs.done, [(10, "SRS")])
            self.assertFalse(docs.deactivated)

    def test_update_deactivates_active_version_before_insert(self) -> None:
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
            self.assertEqual(docs.deactivated, [(10, "DB")])
            self.assertEqual(docs.inserted[0]["status"], "DONE")

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
