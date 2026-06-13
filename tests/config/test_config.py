import logging
import tempfile
import unittest
from pathlib import Path

from config.constants import DocsCode, DocsProgressStatus, UpdateYn, WorkflowStatus
from config.logging_config import configure_logging, get_logger
from config.prompt_settings import PROMPT_PATHS
from config.settings import Settings


class ConfigTest(unittest.TestCase):
    def test_settings_loads_environment_values(self) -> None:
        settings = Settings(
            _env_file=None,
            database_url="sqlite:///test.db",
            qdrant_url="http://localhost:6333",
            llm_base_url="http://localhost:8000/v1",
        )

        self.assertEqual(settings.database_url, "sqlite:///test.db")
        self.assertEqual(settings.qdrant_collection, "arkive")

    def test_constants_match_design_codes(self) -> None:
        self.assertEqual(
            {value.value for value in DocsCode},
            {"SRS", "INTERFACE", "ERD", "DB", "ARCH", "TS"},
        )
        self.assertEqual({value.value for value in UpdateYn}, {"Y", "N"})
        self.assertIn("FAILED", {value.value for value in WorkflowStatus})
        self.assertIn("GENERATING", {value.value for value in DocsProgressStatus})

    def test_prompt_settings_only_contains_paths(self) -> None:
        self.assertTrue(PROMPT_PATHS)
        self.assertTrue(all(isinstance(path, Path) for path in PROMPT_PATHS.values()))

    def test_logging_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            settings = Settings(_env_file=None, log_file=Path(root) / "app.log")
            configure_logging(settings)
            get_logger(__name__).info("config test")

            self.assertTrue(settings.log_file.exists())
            logging.shutdown()


if __name__ == "__main__":
    unittest.main()
