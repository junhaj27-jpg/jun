import unittest
from typing import Any

from tools.result import success_result
from workflow.graph import route_after_preprocess
from workflow.nodes.request_preprocess_node import (
    RequestPreprocessDependencies,
    request_preprocess_node,
)


class ProjectRepositoryStub:
    def __init__(self, exists: bool = True) -> None:
        self.exists = exists

    def exists_project(self, project_sn: int) -> bool:
        return self.exists


class DocsDetailRepositoryStub:
    def __init__(
        self,
        active_srs: dict[str, Any] | None = None,
        active_docs: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.active_srs = active_srs
        self.active_docs = active_docs or {}
        self.generating_calls: list[tuple[int, str]] = []
        self.ensure_generating_calls: list[tuple[int, str]] = []
        self.failed_calls: list[tuple[int, str, str]] = []

    def find_active_srs(self, project_sn: int) -> Any | None:
        return self.active_srs

    def find_active_doc(self, project_sn: int, docs_cd: str) -> Any | None:
        return self.active_docs.get(docs_cd)

    def update_docs_status_generating(self, project_sn: int, docs_cd: str) -> None:
        self.generating_calls.append((project_sn, docs_cd))

    def ensure_docs_status_generating(self, project_sn: int, docs_cd: str) -> None:
        self.ensure_generating_calls.append((project_sn, docs_cd))

    def update_docs_status_failed(
        self, project_sn: int, docs_cd: str, error_message: str
    ) -> None:
        self.failed_calls.append((project_sn, docs_cd, error_message))


class FileRepositoryStub:
    def __init__(self, files: dict[int, dict[str, Any]]) -> None:
        self.files = files

    def find_file_by_sn(self, file_sn: int) -> Any | None:
        return self.files.get(file_sn)

    def find_files_by_sn_list(self, file_sn_list: list[int]) -> list[Any]:
        return [self.files[file_sn] for file_sn in file_sn_list if file_sn in self.files]


def downloader_stub(**kwargs: Any):
    source = kwargs.get("s3_key") or kwargs.get("file_path")
    name = kwargs.get("file_name") or str(source).split("/")[-1]
    return success_result({"local_file_path": f"/tmp/{name}"})


class RequestPreprocessNodeTest(unittest.TestCase):
    def dependencies(
        self,
        files: dict[int, dict[str, Any]],
        *,
        active_srs: dict[str, Any] | None = None,
        active_docs: dict[str, dict[str, Any]] | None = None,
        project_exists: bool = True,
    ) -> tuple[RequestPreprocessDependencies, DocsDetailRepositoryStub]:
        docs_repository = DocsDetailRepositoryStub(active_srs, active_docs)
        return (
            RequestPreprocessDependencies(
                project_repository=ProjectRepositoryStub(project_exists),
                docs_detail_repository=docs_repository,
                file_repository=FileRepositoryStub(files),
                downloader=downloader_stub,
            ),
            docs_repository,
        )

    def test_srs_create_sets_rfp_and_generating(self) -> None:
        dependencies, docs_repository = self.dependencies(
            {
                1: {
                    "file_sn": 1,
                    "file_cd": "FILE_RFP",
                    "s3_key": "rfp/request.pdf",
                    "file_nm": "request.pdf",
                }
            }
        )

        result = request_preprocess_node(
            {"project_sn": 10, "docs_cd": "SRS", "udt_yn": "N", "file_list": [1]},
            dependencies,
        )

        self.assertEqual(result["base_rfp_path"], "/tmp/request.pdf")
        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["next_action"], "SUPERVISOR")
        self.assertEqual(docs_repository.ensure_generating_calls, [(10, "SRS")])
        self.assertEqual(docs_repository.generating_calls, [])

    def test_srs_create_selects_rfp_file_even_when_file_list_has_other_files(self) -> None:
        dependencies, _ = self.dependencies(
            {
                1: {
                    "file_sn": 1,
                    "file_cd": "FILE_MEETING",
                    "s3_key": "meeting/minutes.txt",
                    "file_nm": "minutes.txt",
                },
                2: {
                    "file_sn": 2,
                    "file_cd": "FILE_RFP",
                    "s3_key": "rfp/request.pdf",
                    "file_nm": "request.pdf",
                },
            }
        )

        result = request_preprocess_node(
            {"project_sn": 10, "docs_cd": "SRS", "udt_yn": "N", "file_list": [1, 2]},
            dependencies,
        )

        self.assertEqual(result["input_file_paths"], ["/tmp/minutes.txt", "/tmp/request.pdf"])
        self.assertEqual(result["base_rfp_path"], "/tmp/request.pdf")

    def test_other_create_fails_when_file_list_contains_rfp(self) -> None:
        dependencies, _ = self.dependencies(
            {
                1: {
                    "file_sn": 1,
                    "file_cd": "FILE_RFP",
                    "s3_key": "rfp/request.pdf",
                    "file_nm": "request.pdf",
                },
                10: {"file_sn": 10, "s3_key": "docs/srs.json", "file_nm": "srs.json"},
            },
            active_srs={"file_sn": 10},
        )

        result = request_preprocess_node(
            {"project_sn": 10, "docs_cd": "ERD", "udt_yn": "N", "file_list": [1]},
            dependencies,
        )

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["next_action"], "END")
        self.assertEqual(result["errors"][0]["code"], "RFP_FILE_NOT_ALLOWED")

    def test_db_create_sets_srs_and_erd_paths(self) -> None:
        dependencies, _ = self.dependencies(
            {
                10: {"file_sn": 10, "s3_key": "docs/srs.json", "file_nm": "srs.json"},
                11: {"file_sn": 11, "s3_key": "docs/erd.docx", "file_nm": "erd.docx"},
            },
            active_srs={"file_sn": 10},
            active_docs={"ERD": {"file_sn": 11}},
        )

        result = request_preprocess_node(
            {"project_sn": 10, "docs_cd": "DB", "udt_yn": "N"},
            dependencies,
        )

        self.assertEqual(result["base_requirement_json_path"], "/tmp/srs.json")
        self.assertEqual(result["erd_file_path"], "/tmp/erd.docx")

    def test_ts_create_sets_srs_and_interface_paths(self) -> None:
        dependencies, _ = self.dependencies(
            {
                10: {"file_sn": 10, "file_path": "/repo/srs.json", "file_nm": "srs.json"},
                12: {
                    "file_sn": 12,
                    "s3_key": "docs/interface.docx",
                    "file_nm": "interface.docx",
                },
            },
            active_srs={"file_sn": 10},
            active_docs={"INTERFACE": {"file_sn": 12}},
        )

        result = request_preprocess_node(
            {"project_sn": 10, "docs_cd": "TS", "udt_yn": "N"},
            dependencies,
        )

        self.assertEqual(result["base_requirement_json_path"], "/tmp/srs.json")
        self.assertEqual(result["interface_file_path"], "/tmp/interface.docx")

    def test_other_create_uses_latest_requirement_json_for_erd_arch_and_interface(self) -> None:
        for docs_cd in ("ERD", "ARCH", "INTERFACE"):
            with self.subTest(docs_cd=docs_cd):
                dependencies, _ = self.dependencies(
                    {
                        10: {
                            "file_sn": 10,
                            "file_cd": "FILE_REQ_DOC_JSON",
                            "s3_key": "project/1/SRS/latest.json",
                            "file_nm": "latest.json",
                        }
                    },
                    active_srs={"file_sn": 10},
                )

                result = request_preprocess_node(
                    {"project_sn": 10, "docs_cd": docs_cd, "udt_yn": "N"},
                    dependencies,
                )

                self.assertEqual(result["status"], "READY")
                self.assertEqual(result["base_requirement_json_path"], "/tmp/latest.json")

    def test_other_create_fails_when_latest_requirement_json_is_missing(self) -> None:
        dependencies, _ = self.dependencies({})

        result = request_preprocess_node(
            {"project_sn": 10, "docs_cd": "ERD", "udt_yn": "N"},
            dependencies,
        )

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["next_action"], "END")
        self.assertEqual(result["errors"][0]["code"], "BASE_REQUIREMENT_JSON_NOT_FOUND")

    def test_active_doc_can_use_docs_path_without_file_sn(self) -> None:
        dependencies, _ = self.dependencies(
            {},
            active_srs={"docs_path": "C:/exports/srs.json"},
        )

        result = request_preprocess_node(
            {"project_sn": 10, "docs_cd": "INTERFACE", "udt_yn": "N"},
            dependencies,
        )

        self.assertEqual(result["base_requirement_json_path"], "/tmp/srs.json")

    def test_update_sets_existing_output_and_meeting_paths(self) -> None:
        dependencies, _ = self.dependencies(
            {
                20: {"file_sn": 20, "s3_key": "meeting/minutes.txt", "file_nm": "minutes.txt"},
                21: {"file_sn": 21, "s3_key": "docs/arch.docx", "file_nm": "arch.docx"},
            },
            active_docs={"ARCH": {"file_sn": 21}},
        )

        result = request_preprocess_node(
            {
                "project_sn": 10,
                "docs_cd": "ARCH",
                "udt_yn": "Y",
                "file_list": [20],
            },
            dependencies,
        )

        self.assertEqual(result["input_file_paths"], ["/tmp/minutes.txt"])
        self.assertEqual(result["existing_output_path"], "/tmp/arch.docx")

    def test_srs_update_uses_latest_requirement_json_as_existing_output(self) -> None:
        dependencies, _ = self.dependencies(
            {
                20: {"file_sn": 20, "s3_key": "meeting/minutes.txt", "file_nm": "minutes.txt"},
                30: {"file_sn": 30, "s3_key": "docs/srs.json", "file_nm": "srs.json"},
            },
            active_srs={"file_sn": 30},
            active_docs={"SRS": {"docs_path": "s3://bucket/old-srs.docx"}},
        )

        result = request_preprocess_node(
            {
                "project_sn": 10,
                "docs_cd": "SRS",
                "udt_yn": "Y",
                "file_list": [20],
            },
            dependencies,
        )

        self.assertEqual(result["input_file_paths"], ["/tmp/minutes.txt"])
        self.assertEqual(result["existing_output_path"], "/tmp/srs.json")

    def test_failure_updates_failed_and_skips_supervisor(self) -> None:
        dependencies, docs_repository = self.dependencies({})

        result = request_preprocess_node(
            {"project_sn": 10, "docs_cd": "ERD", "udt_yn": "N"},
            dependencies,
        )

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["next_action"], "END")
        self.assertTrue(docs_repository.failed_calls)
        self.assertEqual(route_after_preprocess(result), "cleanup_node")

    def test_invalid_code_fails_before_supervisor(self) -> None:
        dependencies, _ = self.dependencies({})

        result = request_preprocess_node(
            {"project_sn": 10, "docs_cd": "INVALID", "udt_yn": "N"},  # type: ignore[typeddict-item]
            dependencies,
        )

        self.assertEqual(result["errors"][0]["code"], "INVALID_DOCS_CD")
        self.assertEqual(route_after_preprocess(result), "cleanup_node")

    def test_normalizes_docs_cd_and_udt_yn_before_validation(self) -> None:
        dependencies, docs_repository = self.dependencies(
            {
                1: {
                    "file_sn": 1,
                    "file_cd": "FILE_RFP",
                    "s3_key": "rfp/request.pdf",
                    "file_nm": "request.pdf",
                }
            }
        )

        result = request_preprocess_node(
            {"project_sn": 10, "docs_cd": "srs", "udt_yn": "n", "file_list": [1]},  # type: ignore[typeddict-item]
            dependencies,
        )

        self.assertEqual(result["docs_cd"], "SRS")
        self.assertEqual(result["udt_yn"], "N")
        self.assertEqual(result["status"], "READY")
        self.assertEqual(docs_repository.ensure_generating_calls, [(10, "SRS")])

    def test_interface_create_without_images_records_warning_but_continues(self) -> None:
        dependencies, docs_repository = self.dependencies(
            {10: {"file_sn": 10, "s3_key": "docs/srs.json", "file_nm": "srs.json"}},
            active_srs={"file_sn": 10},
        )

        result = request_preprocess_node(
            {"project_sn": 10, "docs_cd": "INTERFACE", "udt_yn": "N"},
            dependencies,
        )

        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["warnings"][0]["code"], "INTERFACE_IMAGE_LIST_EMPTY")
        self.assertEqual(docs_repository.ensure_generating_calls, [(10, "INTERFACE")])

    def test_update_uses_existing_docs_status_without_insert_fallback(self) -> None:
        dependencies, docs_repository = self.dependencies(
            {
                20: {"file_sn": 20, "s3_key": "meeting/minutes.txt", "file_nm": "minutes.txt"},
                21: {"file_sn": 21, "s3_key": "docs/arch.docx", "file_nm": "arch.docx"},
            },
            active_docs={"ARCH": {"file_sn": 21}},
        )

        result = request_preprocess_node(
            {
                "project_sn": 10,
                "docs_cd": "ARCH",
                "udt_yn": "Y",
                "file_list": [20],
            },
            dependencies,
        )

        self.assertEqual(result["status"], "READY")
        self.assertEqual(docs_repository.generating_calls, [(10, "ARCH")])
        self.assertEqual(docs_repository.ensure_generating_calls, [])


if __name__ == "__main__":
    unittest.main()
