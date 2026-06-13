import os
import json
import uuid
from pathlib import Path
from typing import List, Dict, Any

from parsers import get_parser_for_file
from processors.chunker import split_into_chunks
from processors.document_classifier import classify_document
from processors.section_detector import detect_section_title
from processors.requirement_detector import analyze_requirement
from processors.metadata_builder import build_metadata
from processors.category_mapper import detect_requirement_domain
from processors.requirement_parser import parse_requirement
from schemas import ParsedDocument, ChunkData
from storage.jsonl_writer import JSONLWriter
from config.document_config import DOCUMENT_CATEGORY_MAP


# =========================================================
# 공통 유틸
# =========================================================

def _safe_join(items):
    if not items:
        return ""
    return "\n".join(str(x).strip() for x in items if str(x).strip())


def _build_full_text(req_id, req_name, req):
    parts = [f"[{req_id}] {req_name}"]
    if req.get("definition"):
        parts.append(f"정의:\n{req['definition']}")

    sub_details = _safe_join(req.get("sub_details", []))
    if sub_details:
        parts.append(f"세부내용:\n{sub_details}")

    constraints = _safe_join(req.get("constraints", []))
    if constraints:
        parts.append(f"제약사항:\n{constraints}")

    deliverables = _safe_join(req.get("deliverables", []))
    if deliverables:
        parts.append(f"산출물:\n{deliverables}")

    return "\n\n".join(parts).strip()


# =========================================================
# 일반 문서 (RFP 제외)
# =========================================================

def _process_general_document(file_path: str, doc_spec: Dict, jsonl_writer: JSONLWriter):
    source_name = os.path.basename(file_path)
    knowledge_role = doc_spec["knowledge_role"]
    document_type = doc_spec["document_type"]

    document_category = classify_document(file_path)
    parsed_doc = ParsedDocument.from_dict(get_parser_for_file(file_path)(file_path))

    chunks_out = []
    chunk_idx = 0

    for page in parsed_doc.pages:
        for chunk_text in split_into_chunks(page.text, 700, 100):

            chunk_text = chunk_text.strip()
            if len(chunk_text) < 50:
                continue

            chunk_idx += 1
            chunk_id = str(uuid.uuid4())

            metadata = build_metadata(
                chunk_id=chunk_id,
                text=chunk_text,
                source_name=source_name,
                source_path=file_path,
                page=page.page_number,
                document_category=document_category,
                document_type=document_type,
                knowledge_role=knowledge_role,
                section_title=detect_section_title(chunk_text),
                chunk_index=chunk_idx,
                requirement_analysis=analyze_requirement(
                    chunk_text,
                    knowledge_role=knowledge_role
                ),
                domain_analysis=detect_requirement_domain(chunk_text),
                parsed_requirement={},
                project_name="AI-DLC_AUTOMATION"
            )

            chunk_obj = ChunkData.from_values(
                chunk_id=chunk_id,
                content=chunk_text,
                meta_dict=metadata
            )

            jsonl_writer.write_chunk(chunk_obj)
            chunks_out.append(chunk_obj.to_dict())

    return {"chunks": chunks_out}


# =========================================================
# PIPELINE
# =========================================================

def run_phase1_pipeline(file_path: str):

    input_path = Path(file_path)

    print(f"\n[Processing] 📄 {input_path.name}")

    try:
        doc_category = classify_document(file_path)

        doc_spec = DOCUMENT_CATEGORY_MAP.get(
            doc_category,
            {"document_type": "UNKNOWN", "knowledge_role": "GENERAL"}
        )

        if doc_category == "RFP":
            print(f"⏭️ RFP 문서는 요구사항추출.py에서 JSON으로 처리하므로 전처리에서 제외: {input_path.name}")
            return {"chunks": []}

        jsonl_writer = JSONLWriter(
            f"./output/chunks/{input_path.stem}_chunks.jsonl",
            overwrite=True
        )

        result = _process_general_document(file_path, doc_spec, jsonl_writer)

        print(f"✨ 완료: {input_path.name} → chunks={len(result['chunks'])}")

        return result

    except Exception as e:
        import traceback
        print(f"❌ 실패: {input_path.name} → {e}")
        traceback.print_exc()
        return {"chunks": []}
    
if __name__ == "__main__":
    print("=" * 60 + "\n🤖 AI-DLC 전처리 파이프라인\n" + "=" * 60)
    TARGET_DIRS, SUPPORTED_EXTENSIONS = [
        "./data/강제 규정",
        "./data/기술",
        "./data/요구사항 가이드",
        "./data/용어사전",
        "./data/GDS",
    ], [".pdf", ".docx", ".txt", ".md"]
    total_files = total_chunks = 0
    
    for dir_path in TARGET_DIRS:
        target_path = Path(dir_path)
        if not target_path.exists():
            print(f"⚠️ 폴더 없음: {dir_path}"); continue
        print(f"\n📂 [{target_path.name}] 스캔 중...")
        for file in sorted(target_path.iterdir()):
            if file.is_file() and file.suffix.lower() in SUPPORTED_EXTENSIONS and not file.name.startswith("~$"):
                res = run_phase1_pipeline(str(file))
                total_files += 1
                total_chunks += len(res["chunks"])
                
    print(f"\n{'='*60}\n🎉 전처리 완료\n처리 문서: {total_files}개\n생성 chunk: {total_chunks}개\n{'='*60}")
