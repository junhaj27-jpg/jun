import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


def build_erd_output_paths(prj_sn: int | None = None, timestamp: str | None = None) -> dict[str, str]:
    timestamp = timestamp or datetime.now().strftime("%Y%m%d%H%M%S")
    if prj_sn is None:
        base_dir = Path("./output/erd")
        prefix = "local"
    else:
        base_dir = Path(os.getenv("STORAGE_ROOT", "./storage")) / "projects" / str(prj_sn) / "docs" / "erd"
        prefix = str(prj_sn)
    base_dir.mkdir(parents=True, exist_ok=True)
    return {
        "docx_path": str(base_dir / f"erd_design_{prefix}_{timestamp}.docx"),
        "image_path": str(base_dir / f"erd_image_{prefix}_{timestamp}.png"),
        "json_path": str(base_dir / f"erd_design_{prefix}_{timestamp}.json"),
        "mmd_path": str(base_dir / f"erd_design_{prefix}_{timestamp}.mmd"),
    }


def save_erd_json(final_erd_json: dict[str, Any], json_path: str) -> None:
    Path(json_path).parent.mkdir(parents=True, exist_ok=True)
    Path(json_path).write_text(json.dumps(final_erd_json, ensure_ascii=False, indent=2), encoding="utf-8")


def save_mermaid_code(mermaid_code: str, mmd_path: str) -> None:
    Path(mmd_path).parent.mkdir(parents=True, exist_ok=True)
    Path(mmd_path).write_text(mermaid_code, encoding="utf-8")
