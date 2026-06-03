import copy
from pathlib import Path
from typing import Any


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def set_cell(cell, value: Any) -> None:
    cell.text = clean_text(value)


def clone_table_after(table):
    new_tbl = copy.deepcopy(table._tbl)
    table._tbl.addnext(new_tbl)


def save_docx_with_fallback(doc, output_path: str) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    for idx in range(0, 100):
        candidate = path if idx == 0 else path.with_name(f"{path.stem}_{idx}{path.suffix}")
        try:
            doc.save(str(candidate))
            return str(candidate)
        except PermissionError:
            continue

    raise PermissionError(f"DOCX 저장 실패: {output_path} 및 대체 파일명을 사용할 수 없습니다.")
