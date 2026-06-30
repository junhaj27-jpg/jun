# 기존 산출물을 구조화된 JSON 데이터로 변환합니다.

import json
from pathlib import Path
from typing import Any

from config.constants import normalize_docs_cd
from tools.parser.db_design_docx_parser import parse_db_design_docx
from tools.parser.docx_parser import parse_docx
from tools.parser.erd_docx_parser import parse_erd_docx
from tools.parser.pdf_parser import parse_pdf
from tools.parser.ts_docx_parser import parse_ts_docx
from tools.result import ToolResult, error_result, success_result


def parse_artifact(file_path: str) -> ToolResult:
    path = Path(file_path)
    try:
        if path.suffix.lower() == ".json":
            return success_result(
                {"file_path": str(path), "raw_json": json.loads(path.read_text(encoding="utf-8"))}
            )
        if path.suffix.lower() == ".docx":
            return _as_artifact(parse_docx(file_path))
        if path.suffix.lower() == ".pdf":
            return _as_artifact(parse_pdf(file_path))
        if path.suffix.lower() in {".md", ".txt"}:
            text = path.read_text(encoding="utf-8")
            return success_result({"file_path": str(path), "text": text, "items": [{"text": text}]})
        return error_result("ARTIFACT_FORMAT_UNSUPPORTED", f"지원하지 않는 문서 형식입니다: {path.suffix}")
    except Exception as exc:
        return error_result("ARTIFACT_PARSE_FAILED", str(exc), {"file_path": file_path})


def parse_existing_artifact(file_path: str, docs_cd: str) -> ToolResult:
    """산출물 종류에 맞는 Document Merge 공용 파서로 기존 문서를 읽습니다."""

    normalized = normalize_docs_cd(docs_cd)
    if str(file_path).lower().endswith(".docx"):
        specialized = {
            "ERD": parse_erd_docx,
            "DB": parse_db_design_docx,
            "TS": parse_ts_docx,
        }.get(normalized)
        if specialized is not None:
            parsed = specialized(str(file_path))
            if parsed["success"]:
                return parsed
    return parse_artifact(str(file_path))


def artifact_items(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return [data] if data is not None else []
    if "raw_json" in data:
        return artifact_items(data["raw_json"])
    if isinstance(data.get("final_document_json"), dict):
        return artifact_items(data["final_document_json"])
    if isinstance(data.get("result"), dict):
        result = data["result"]
        if isinstance(result.get("final_document_json"), dict):
            return artifact_items(result["final_document_json"])
    for key in (
        "requirements",
        "requirement_json_list",
        "final_requirement_json_list",
        "final_requirements",
        "integrated_requirement_json_list",
        "integrated_artifact_json_list",
        "interface_json_list",
        "test_case_json_list",
        "items",
        "tables",
        "screens",
        "scenarios",
    ):
        if isinstance(data.get(key), list):
            return data[key]
    return [data] if data else []


def _as_artifact(result: ToolResult) -> ToolResult:
    if not result["success"]:
        return result
    data = result["data"]
    items = data.get("paragraphs") or data.get("pages") or []
    return success_result({**data, "items": items})
