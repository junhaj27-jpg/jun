import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
import re
import fitz
from processors.cleaner import clean_text
from typing import Dict, Any, List

EXTRACT_TABLES = False

# EasyOCR 리더 초기화 (오류 방지를 위해 전역 선언)
try:
    import easyocr
    import numpy as np
    reader = easyocr.Reader(['ko', 'en'])
except:
    np = None
    reader = None

def parse_pdf(file_path: str) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

    # [수정] 대괄호 유무 상관없이 ID 패턴을 잡도록 정규식 완화
    req_pattern = re.compile(r"([A-Z]+-\d+)")
    doc = fitz.open(file_path)
    
    global_full_text_lines = []
    pages_content = []

    for idx, page in enumerate(doc):
        page_num = idx + 1
        layout_blocks = []
        table_map = []
        
        # 1. 테이블 추출
        if EXTRACT_TABLES:
            for table in page.find_tables():
                raw_data = table.extract()
                # 표 내용을 문자열로 미리 변환
                table_text = "\n".join([" | ".join([str(c) for c in row if c]) for row in raw_data])
                req_match = req_pattern.search(table_text)
                table_map.append({
                    "rect": fitz.Rect(table.bbox),
                    "rows": raw_data,
                    "text": table_text,
                    "is_requirement": bool(req_match),
                    "requirement_id": req_match.group(1) if req_match else None
                })

        # 2. 텍스트 추출 (OCR 포함)
        blocks = page.get_text("blocks")
        if not blocks and reader and np is not None:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img_np = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
            merged_text = clean_text("\n".join(reader.readtext(img_np, detail=0)))
        else:
            blocks.sort(key=lambda b: (round(b[1], 1), round(b[0], 1)))
            processed = [b[4].strip() for b in blocks if not any(fitz.Rect(b[:4]).intersects(t["rect"]) for t in table_map) and b[4].strip()]
            merged_text = clean_text("\n".join(processed))

        # [핵심] 3. 페이지 텍스트에 표를 강제로 붙임 (청커가 인식하도록)
        page_text_content = merged_text
        for t in table_map:
            page_text_content += f"\n[요구사항 ID: {t['requirement_id'] if t['is_requirement'] else 'NONE'}]\n{t['text']}"
            layout_blocks.append({"type": "table", "rows": t["rows"], "is_requirement": t["is_requirement"], "requirement_id": t["requirement_id"]})
        
        layout_blocks.append({"type": "paragraph", "text": merged_text, "is_requirement": bool(req_pattern.search(page_text_content)), "requirement_id": None})

        pages_content.append({"page_number": page_num, "text": page_text_content, "layout_blocks": layout_blocks})
        global_full_text_lines.append(page_text_content)

    doc.close()
    return {"text": "\n".join(global_full_text_lines), "pages": pages_content, "source_name": os.path.basename(file_path)}

def extract_requirements_from_pdf(file_path: str) -> List[Dict[str, Any]]:
    data = parse_pdf(file_path)
    extracted = []
    for page in data["pages"]:
        for block in page["layout_blocks"]:
            if block["type"] == "table" and block.get("is_requirement"):
                extracted.append({
                    "original_req_id": block["requirement_id"],
                    "requirement_name": str(block["rows"][0][1] if len(block["rows"][0]) > 1 else block["rows"][0][0]),
                    "raw_text": str(block["rows"]),
                    "source_name": data["source_name"],
                    "page": page["page_number"]
                })
    return extracted
