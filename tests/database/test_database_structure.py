import inspect
import unittest

from sqlalchemy.orm import Session

from database.base import Base
from database.engine import create_database_engine
from database.models import (
    ArchitectureConfig,
    Docs,
    DocsDetail,
    File,
    Project,
)
from database.repositories import DocsDetailRepository, FileRepository
from database.session import SessionLocal


class DatabaseStructureTest(unittest.TestCase):
    def test_engine_creation_does_not_connect(self) -> None:
        engine = create_database_engine("sqlite:///:memory:")

        self.assertEqual(engine.url.drivername, "sqlite")

    def test_models_are_registered(self) -> None:
        self.assertEqual(
            set(Base.metadata.tables),
            {
                "tbl_project",
                "tbl_docs",
                "tbl_docs_detail",
                "tbl_file",
                "tbl_architecture_config",
            },
        )
        self.assertTrue(all(model.__table__ is not None for model in [Project, Docs, DocsDetail, File, ArchitectureConfig]))

    def test_repository_signatures_exist(self) -> None:
        docs_methods = {
            "find_active_srs",
            "find_active_doc",
            "update_docs_status_generating",
            "update_docs_status_done",
            "update_docs_status_failed",
            "insert_docs_detail",
        }
        file_methods = {"find_file_by_sn", "find_files_by_sn_list", "insert_file"}

        self.assertTrue(docs_methods.issubset(vars(DocsDetailRepository)))
        self.assertTrue(file_methods.issubset(vars(FileRepository)))
        self.assertIn("error_message", inspect.signature(DocsDetailRepository.update_docs_status_failed).parameters)

    def test_repository_is_placeholder(self) -> None:
        session: Session = SessionLocal()
        try:
            repository = DocsDetailRepository(session)
            with self.assertRaises(NotImplementedError):
                repository.find_active_srs(1)
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
