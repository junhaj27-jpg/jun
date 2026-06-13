from typing import Any

from sqlalchemy.orm import Session

from schemas.common.file_schema import FileSn


class FileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_file_by_sn(self, file_sn: FileSn) -> Any | None:
        raise NotImplementedError

    def find_files_by_sn_list(self, file_sn_list: list[FileSn]) -> list[Any]:
        raise NotImplementedError

    def insert_file(
        self,
        *,
        file_nm: str,
        file_path: str,
        file_size: int,
        file_extn: str,
    ) -> Any:
        raise NotImplementedError
