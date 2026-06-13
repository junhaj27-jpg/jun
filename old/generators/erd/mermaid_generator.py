import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import requests

from generators.common.mermaid_renderer import render_mermaid_ink_image
from generators.erd.docx_adapter import final_erd_to_template_erd
from generators.erd.docx_generator import render_basic_erd_image


def generate_mermaid_code(final_erd_json: dict[str, Any]) -> str:
    lines = ["erDiagram"]
    for rel in final_erd_json.get("relationships", []):
        from_table = sanitize_identifier(rel.get("from_table"))
        to_table = sanitize_identifier(rel.get("to_table"))
        if from_table and to_table:
            lines.append(f"    {from_table} ||--o{{ {to_table} : has")

    for table in final_erd_json.get("tables", []):
        table_name = sanitize_identifier(table.get("table_name")) or "unknown"
        lines.append(f"    {table_name} {{")
        for col in table.get("columns", []):
            data_type = sanitize_type(col.get("data_type"))
            col_name = sanitize_identifier(col.get("column_name")) or "unknown_col"
            keys = []
            if col.get("is_pk"):
                keys.append("PK")
            if col.get("is_fk"):
                keys.append("FK")
            suffix = " " + " ".join(keys) if keys else ""
            lines.append(f"        {data_type} {col_name}{suffix}")
        lines.append("    }")
    return "\n".join(lines)


def render_mermaid_by_api(mermaid_code: str, output_path: str) -> str | None:
    api_url = os.getenv("MERMAID_RENDER_API_URL", "").strip()
    if not api_url:
        return render_mermaid_ink_image(mermaid_code, output_path)

    try:
        response = requests.post(api_url, json={"code": mermaid_code}, timeout=20)
        response.raise_for_status()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        return str(path)
    except Exception:
        return None


def render_mermaid_by_cli(mermaid_code: str, output_path: str) -> str | None:
    mmd_path = Path(output_path).with_suffix(".mmd")
    mmd_path.parent.mkdir(parents=True, exist_ok=True)
    mmd_path.write_text(mermaid_code, encoding="utf-8")

    mmdc_path = os.getenv("MMDC_PATH") or shutil.which("mmdc")
    if not mmdc_path:
        return None

    try:
        subprocess.run([mmdc_path, "-i", str(mmd_path), "-o", output_path, "-b", "white"], check=True)
        return output_path
    except Exception:
        return None


def render_erd_image(final_erd_json: dict[str, Any], mermaid_code: str, output_path: str) -> str | None:
    image_path = render_mermaid_by_api(mermaid_code, output_path)
    if image_path:
        return image_path
    image_path = render_mermaid_by_cli(mermaid_code, output_path)
    if image_path:
        return image_path
    return render_basic_erd_image(final_erd_to_template_erd(final_erd_json), output_path)


def sanitize_identifier(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^0-9A-Za-z_]", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if text and text[0].isdigit():
        text = "_" + text
    return text


def sanitize_type(value: Any) -> str:
    text = str(value or "VARCHAR").strip().upper()
    text = re.sub(r"[^0-9A-Za-z_]", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "VARCHAR"
