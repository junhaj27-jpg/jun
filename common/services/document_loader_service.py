from pathlib import Path
from typing import Any

from common.db.repositories.docs_repository import get_docs_detail_by_docs_sn
from common.db.repositories.file_repository import get_file_by_file_sn, get_files_by_file_sns
from common.files.file_reader import read_file_text
from common.parsers.requirement_parser import parse_requirement_to_json


def load_requirement_document(
    prj_sn: int,
    requirement_docs_sn: int | None = None,
    requirement_file_sn: int | None = None,
) -> dict[str, Any]:
    if requirement_docs_sn:
        row = get_docs_detail_by_docs_sn(prj_sn, requirement_docs_sn)
        file_path = row["docs_path"]
        file_ext = Path(file_path).suffix.lstrip(".")
        text = read_file_text(file_path, file_ext)
        return {
            "source_type": "docs",
            "source_sn": requirement_docs_sn,
            "file_path": file_path,
            "file_ext": file_ext,
            "text": text,
            "requirement_json": parse_requirement_to_json(text),
            "metadata": row,
        }

    if requirement_file_sn:
        row = get_file_by_file_sn(prj_sn, requirement_file_sn)
        file_path = row["file_path"]
        file_ext = row.get("file_ext") or Path(file_path).suffix.lstrip(".")
        text = read_file_text(file_path, file_ext)
        return {
            "source_type": "file",
            "source_sn": requirement_file_sn,
            "file_path": file_path,
            "file_ext": file_ext,
            "text": text,
            "requirement_json": parse_requirement_to_json(text),
            "metadata": row,
        }

    raise ValueError("requirement_docs_sn 또는 requirement_file_sn 중 하나가 필요합니다.")


def load_meeting_documents(prj_sn: int, meeting_file_sns: list[int]) -> dict[str, Any]:
    rows = get_files_by_file_sns(prj_sn, meeting_file_sns)
    files = []
    texts = []

    for row in rows:
        file_path = row["file_path"]
        file_ext = row.get("file_ext") or Path(file_path).suffix.lstrip(".")
        text = read_file_text(file_path, file_ext)
        item = {
            "file_sn": row["file_sn"],
            "file_nm": row.get("file_nm"),
            "file_path": file_path,
            "file_ext": file_ext,
            "text": text,
        }
        files.append(item)
        texts.append(f"[{row.get('file_nm') or row['file_sn']}]\n{text}")

    return {"files": files, "merged_text": "\n\n".join(texts)}
