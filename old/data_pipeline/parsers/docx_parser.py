import os
from typing import Dict, Any, List
import docx

from docx.table import Table
from docx.text.paragraph import Paragraph

from processors.cleaner import clean_text


PARA_PER_VIRTUAL_PAGE = 300


def parse_docx(file_path: str) -> Dict[str, Any]:

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"파일 없음: {file_path}")

    doc_obj = docx.Document(file_path)

    all_lines: List[str] = []

    layout_blocks = []

    def iter_block_items(parent):

        from docx.document import Document as DocType
        from docx.oxml.table import CT_Tbl
        from docx.oxml.text.paragraph import CT_P

        parent_elm = (
            parent.element.body
            if isinstance(parent, DocType)
            else parent.element
        )

        for child in parent_elm.iterchildren():

            if isinstance(child, CT_P):
                yield Paragraph(child, parent)

            elif isinstance(child, CT_Tbl):
                yield Table(child, parent)

    for block in iter_block_items(doc_obj):

        # =========================
        # PARAGRAPH
        # =========================

        if isinstance(block, Paragraph):

            text = clean_text(block.text.strip())

            if not text:
                continue

            style = (
                block.style.name.lower()
                if block.style
                else ""
            )

            heading_level = None

            if "heading 1" in style:
                text = f"# {text}"
                heading_level = 1

            elif "heading 2" in style:
                text = f"## {text}"
                heading_level = 2

            elif "heading 3" in style:
                text = f"### {text}"
                heading_level = 3

            all_lines.append(text)

            layout_blocks.append({
                "type": "heading" if heading_level else "paragraph",
                "level": heading_level,
                "text": text
            })

        # =========================
        # TABLE
        # =========================

        elif isinstance(block, Table):

            structured_rows = []

            for row in block.rows:

                row_cells = []

                for cell in row.cells:

                    cell_text = clean_text(
                        cell.text.strip()
                        .replace("\n", " ")
                        .replace("\r", " ")
                    )

                    if (
                        cell_text
                        and (
                            not row_cells
                            or row_cells[-1] != cell_text
                        )
                    ):
                        row_cells.append(cell_text)

                if row_cells:

                    structured_rows.append(row_cells)

                    all_lines.append(
                        "| " + " | ".join(row_cells) + " |"
                    )

            layout_blocks.append({
                "type": "table",
                "rows": structured_rows
            })

    combined = "\n".join(all_lines)

    cleaned = clean_text(combined)

    # =========================
    # VIRTUAL PAGES
    # =========================

    pages = []

    current_page = []
    current_layout = []

    for idx, line in enumerate(all_lines):

        current_page.append(line)

        if idx < len(layout_blocks):
            current_layout.append(layout_blocks[idx])

        if len(current_page) >= PARA_PER_VIRTUAL_PAGE:

            pages.append({
                "page_number": len(pages) + 1,
                "text": "\n".join(current_page),
                "layout_blocks": current_layout
            })

            current_page = []
            current_layout = []

    if current_page:

        pages.append({
            "page_number": len(pages) + 1,
            "text": "\n".join(current_page),
            "layout_blocks": current_layout
        })

    return {
        "text": cleaned,
        "pages": pages,
        "source_path": file_path,
        "source_name": os.path.basename(file_path),
        "document_type": "DOCX"
    }