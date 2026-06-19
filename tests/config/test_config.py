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
            db_host="localhost",
            db_port=3306,
            db_name="alpled_db",
            db_user="alpled",
            db_password="password",
            qdrant_url="http://localhost:6333",
            llm_base_url="http://localhost:8000/v1",
        )

        self.assertEqual(
            settings.resolved_database_url,
            "mysql+pymysql://alpled:password@localhost:3306/alpled_db",
        )
        self.assertEqual(settings.alpled_reference_collection, "ALPLED_reference")

    def test_settings_builds_database_url_from_db_parts(self) -> None:
        settings = Settings(
            _env_file=None,
            db_host="localhost",
            db_port=3306,
            db_name="alpled_db",
            db_user="alpled",
            db_password="p@ss word",
        )

        self.assertEqual(
            settings.resolved_database_url,
            "mysql+pymysql://alpled:p%40ss+word@localhost:3306/alpled_db",
        )

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
