import tempfile
import unittest
from pathlib import Path

from config.settings import Settings
from tools.storage.cleanup_manager import cleanup_workflow_resources
from tools.storage.downloader import download_file
from tools.storage.uploader import upload_file


class S3ClientStub:
    def __init__(self) -> None:
        self.download_calls: list[tuple[str, str, str]] = []
        self.upload_calls: list[tuple[str, str, str]] = []

    def download_file(self, bucket: str, key: str, target: str) -> None:
        self.download_calls.append((bucket, key, target))
        Path(target).write_text("downloaded", encoding="utf-8")

    def upload_file(self, source: str, bucket: str, key: str) -> None:
        self.upload_calls.append((source, bucket, key))


class StorageToolsTest(unittest.TestCase):
    def test_s3_download_uses_repository_resolved_s3_key(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            client = S3ClientStub()
            settings = Settings(_env_file=None, s3_bucket="bucket")

            result = download_file(
                s3_key="project/input.pdf",
                file_name="input.pdf",
                destination_dir=root,
                s3_client=client,
                settings=settings,
            )

            self.assertTrue(result["success"])
            self.assertEqual(client.download_calls[0][0:2], ("bucket", "project/input.pdf"))

    def test_s3_upload_uses_injected_client(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "output.docx"
            source.write_text("output", encoding="utf-8")
            client = S3ClientStub()
            settings = Settings(_env_file=None, s3_bucket="bucket")

            result = upload_file(
                str(source),
                s3_key="project/output.docx",
                s3_client=client,
                settings=settings,
            )

            self.assertTrue(result["success"])
            self.assertEqual(client.upload_calls[0][1:], ("bucket", "project/output.docx"))

    def test_cleanup_workflow_resources_protects_export(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            storage = Path(root)
            input_dir = storage / "input"
            temp_dir = storage / "temp"
            extracted_dir = storage / "extracted_images"
            mermaid_dir = storage / "mermaid"
            output_dir = storage / "output"
            for directory in [input_dir, temp_dir, extracted_dir, mermaid_dir, output_dir]:
                directory.mkdir()

            input_file = input_dir / "input.pdf"
            temp_file = temp_dir / "work.tmp"
            extracted_file = extracted_dir / "image.png"
            mermaid_file = mermaid_dir / "diagram.mmd"
            export_file = output_dir / "result.docx"
            for path in [input_file, temp_file, extracted_file, mermaid_file, export_file]:
                path.write_text("data", encoding="utf-8")

            settings = Settings(
                _env_file=None,
                local_storage_root=storage,
                input_dir=input_dir,
                output_dir=output_dir,
                temp_dir=temp_dir,
                extract_image_dir=extracted_dir,
                mermaid_dir=mermaid_dir,
            )
            state = {
                "input_file_paths": [str(input_file)],
                "input_image_paths": [],
                "export_result": {"local_file_path": str(export_file)},
            }

            result = cleanup_workflow_resources(state, settings=settings)

            self.assertTrue(result["success"])
            self.assertFalse(input_file.exists())
            self.assertFalse(temp_dir.exists())
            self.assertFalse(extracted_dir.exists())
            self.assertFalse(mermaid_dir.exists())
            self.assertTrue(export_file.exists())

    def test_cleanup_workflow_resources_cleans_reference_paths_and_protects_formats(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as root:
            storage = Path(root)
            input_dir = storage / "input"
            temp_dir = storage / "temp"
            extracted_dir = storage / "extracted_images"
            mermaid_dir = storage / "mermaid"
            output_dir = storage / "output"
            for directory in [input_dir, temp_dir, extracted_dir, mermaid_dir, output_dir]:
                directory.mkdir()

            base_rfp = input_dir / "rfp.pdf"
            requirement = input_dir / "srs.json"
            erd = input_dir / "erd.docx"
            interface = input_dir / "interface.docx"
            existing = input_dir / "existing.docx"
            docx = output_dir / "result.docx"
            pdf = output_dir / "result.pdf"
            hwp = output_dir / "result.hwp"
            for path in [base_rfp, requirement, erd, interface, existing, docx, pdf, hwp]:
                path.write_text("data", encoding="utf-8")

            settings = Settings(
                _env_file=None,
                local_storage_root=storage,
                input_dir=input_dir,
                output_dir=output_dir,
                temp_dir=temp_dir,
                extract_image_dir=extracted_dir,
                mermaid_dir=mermaid_dir,
            )
            result = cleanup_workflow_resources(
                {
                    "base_rfp_path": str(base_rfp),
                    "base_requirement_json_path": str(requirement),
                    "erd_file_path": str(erd),
                    "interface_file_path": str(interface),
                    "existing_output_path": str(existing),
                    "export_result": {
                        "docx_path": str(docx),
                        "pdf_path": str(pdf),
                        "hwp_path": str(hwp),
                    },
                },
                settings=settings,
            )

            self.assertTrue(result["success"])
            for path in [base_rfp, requirement, erd, interface, existing]:
                self.assertFalse(path.exists())
            for path in [docx, pdf, hwp]:
                self.assertTrue(path.exists())

    def test_cleanup_workflow_resources_cleans_explicit_temp_lists(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            storage = Path(root)
            temp_dir = storage / "temp"
            extracted_dir = storage / "extracted_images"
            mermaid_dir = storage / "mermaid"
            output_dir = storage / "output"
            for directory in [temp_dir, extracted_dir, mermaid_dir, output_dir]:
                directory.mkdir()

            temp_file = temp_dir / "middle.tmp"
            extracted_image = extracted_dir / "screen.png"
            mermaid_file = mermaid_dir / "diagram.mmd"
            export_file = output_dir / "result.docx"
            for path in [temp_file, extracted_image, mermaid_file, export_file]:
                path.write_text("data", encoding="utf-8")

            settings = Settings(
                _env_file=None,
                local_storage_root=storage,
                output_dir=output_dir,
                temp_dir=temp_dir,
                extract_image_dir=extracted_dir,
                mermaid_dir=mermaid_dir,
            )
            result = cleanup_workflow_resources(
                {
                    "temp_file_paths": [str(temp_file)],
                    "extracted_image_paths": [str(extracted_image)],
                    "mermaid_file_paths": [str(mermaid_file)],
                    "export_result": {"local_file_path": str(export_file)},
                },
                settings=settings,
            )

            self.assertTrue(result["success"])
            self.assertFalse(temp_file.exists())
            self.assertFalse(extracted_image.exists())
            self.assertFalse(mermaid_file.exists())
            self.assertTrue(export_file.exists())


if __name__ == "__main__":
    unittest.main()
