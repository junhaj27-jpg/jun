import json
import glob
import os
from typing import List
from phase0_schema import CanonicalRequirement, RequirementDocument
import re 
# =========================================================
# 유틸
# =========================================================

def load_jsonl(file_path: str):
    rows = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if (line := line.strip()):
                rows.append(json.loads(line))
    return rows

def normalize_requirement_type(value):
    val = str(value).upper()
    return "비기능" if val in ["NON_FUNCTIONAL", "비기능"] else "기능"

# =========================================================
# 데이터 변환
# =========================================================

# def transform_chunk_to_requirement(chunk: dict):
#     meta = chunk.get("metadata", {})
    
#     # 필터링 조건
#     if meta.get("document_category") != "RFP" or \
#        meta.get("knowledge_role") != "GENERATION_SOURCE" or \
#        not meta.get("is_requirement"):
#         return None

#     req_id = meta.get("req_id") or meta.get("section") or "REQ-UNKNOWN"
#     req_name = meta.get("requirement_name") or meta.get("title") or req_id
#     full_text = chunk.get("page_content") or meta.get("text", "")
#     req_type = normalize_requirement_type(meta.get("requirement_type", "기능"))

#     # 검증 기준 및 제약사항 추출
#     lines = full_text.split("\n")
#     validation_criteria = [l.strip() for l in lines if any(k in l for k in ["확인", "검증", "테스트", "가능해야", "지원해야"])]
#     constraints = [l.strip() for l in lines if any(k in l for k in ["하여야 한다", "필수", "반드시", "금지", "제한"])]

#     return CanonicalRequirement(
#         requirement_id=req_id,
#         requirement_name=req_name,
#         requirement_type=req_type,
#         description=full_text,
#         source=[meta.get("source_name", "Unknown")],
#         constraints=list(set(constraints)),
#         priority="중",
#         validation_criteria=list(set(validation_criteria)),
#         note=None
#     )

def transform_chunk_to_requirement(chunk: dict):
    meta = chunk.get("metadata", {})
    full_text = chunk.get("full_text_content") or chunk.get("page_content", "")
    
    # 1. 판정 (이전 단계에서 정의한 is_requirement 로직 활용 권장)
    req_match = re.search(r"\[(REQ-\d+)\]", full_text)
    if not (meta.get("requirement_signal", False) or bool(req_match)):
        return None

    # 2. 기본 정보 추출
    req_id = req_match.group(1) if req_match else "REQ-UNKNOWN"
    
    # 요구사항 명칭을 더 정밀하게 추출 (패턴 다양화 대응)
    name_patterns = [r"요구사항 명\s*\|\s*(.*?)(?:\n|\|)", r"요구사항 명칭\s*\|\s*(.*?)(?:\n|\|)"]
    req_name = f"요구사항_{req_id}"
    for p in name_patterns:
        if m := re.search(p, full_text):
            req_name = m.group(1).strip()
            break

    # 3. 구조적 추출 (개조식 패턴 중심)
    lines = [l.strip(" ㅇ-●■") for l in full_text.split("\n") if l.strip(" ㅇ-●■")]
    
    # 제약사항: "~해야 함", "필수", "반드시" 등이 포함된 문장
    constraints = [l for l in lines if any(k in l for k in ["해야", "하여야", "필수", "반드시", "금지", "제한"])]
    
    # 검증 기준: "확인", "제출", "지원", "증빙" 등이 포함된 문장
    validation_criteria = [l for l in lines if any(k in l for k in ["확인", "제출", "지원", "검토", "증빙"])]

    # 4. CanonicalRequirement 생성
    return CanonicalRequirement(
        requirement_id=req_id,
        requirement_name=req_name,
        requirement_type="비기능" if any(k in full_text for k in ["보안", "성능", "품질"]) else "기능",
        description=full_text, # 원본은 유지하여 추적성 확보
        source=[meta.get("source_name", "Unknown")],
        constraints=list(set(constraints)),
        priority="중",
        validation_criteria=list(set(validation_criteria)),
        note=None
    )

def deduplicate_requirements(requirements: List[CanonicalRequirement]):
    unique = {(req.requirement_id, req.description[:100]): req for req in requirements}
    return list(unique.values())

# =========================================================
# 메인 실행
# =========================================================

def run_phase2():
    input_files = glob.glob("./*_final.json")
    os.makedirs("./output/requirements", exist_ok=True)

    for file_path in input_files:
        filename = os.path.basename(file_path)
        print(f"\n[LOAD] {filename}")

        with open(file_path, "r", encoding="utf-8") as f:
            req_doc = RequirementDocument(**json.load(f))

        req_doc.requirements = deduplicate_requirements(req_doc.requirements)
        base_name = filename.replace("_final.json", "")
        output_path = f"./output/requirements/{base_name}_requirements.json"

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(req_doc.model_dump_json(indent=4, ensure_ascii=False))
        
        print(f"[SAVE] {output_path} ({len(requirements)}개)")

    print("\n" + "=" * 60 + "\nPhase2 완료\n" + "=" * 60)

if __name__ == "__main__":
    run_phase2()
