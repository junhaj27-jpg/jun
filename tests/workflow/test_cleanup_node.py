import tempfile
import unittest
from pathlib import Path

from config.settings import Settings
from tools.result import error_result
from workflow.nodes.cleanup_node import CleanupDependencies, cleanup_node


class CleanupNodeTest(unittest.TestCase):
    def test_cleanup_node_runs_without_overwriting_success_status(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            storage = Path(root)
            input_dir = storage / "input"
            temp_dir = storage / "temp"
            extracted_dir = storage / "extracted_images"
            mermaid_dir = storage / "mermaid"
            output_dir = storage / "output"
            for directory in [input_dir, temp_dir, extracted_dir, mermaid_dir, output_dir]:
                directory.mkdir()

            input_file = input_dir / "request.pdf"
            export_file = output_dir / "result.docx"
            input_file.write_text("input", encoding="utf-8")
            export_file.write_text("export", encoding="utf-8")
            settings = Settings(
                _env_file=None,
                local_storage_root=storage,
                input_dir=input_dir,
                output_dir=output_dir,
                temp_dir=temp_dir,
                extract_image_dir=extracted_dir,
                mermaid_dir=mermaid_dir,
            )

            result = cleanup_node(
                {
                    "status": "DONE",
                    "input_file_paths": [str(input_file)],
                    "export_result": {"local_file_path": str(export_file)},
                    "warnings": [],
                },
                CleanupDependencies(settings=settings),
            )

            self.assertEqual(result["status"], "DONE")
            self.assertFalse(input_file.exists())
            self.assertTrue(export_file.exists())
            self.assertIn("removed_paths", result["cleanup_result"])

    def test_cleanup_node_records_warning_on_cleanup_failure(self) -> None:
        def failed_cleanup(*args, **kwargs):
            return error_result("CLEANUP_PARTIAL_FAILED", "일부 정리 실패", {"paths": []})

        state = {"status": "FAILED", "warnings": []}
        result = cleanup_node(
            state,
            CleanupDependencies(cleanup_manager=failed_cleanup),
        )

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["warnings"][0]["code"], "CLEANUP_PARTIAL_FAILED")
        self.assertEqual(result["cleanup_result"]["code"], "CLEANUP_PARTIAL_FAILED")


if __name__ == "__main__":
    unittest.main()
