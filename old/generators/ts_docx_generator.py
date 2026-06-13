from typing import Any

from TS.TS_agent import convert_to_docx


def generate_ts_docx(data: dict[str, Any], output_path: str) -> str:
    convert_to_docx(data, output_path)
    return output_path
