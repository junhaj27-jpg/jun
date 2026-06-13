import os
from typing import Dict, Any
from processors.cleaner import clean_text

def parse_text(file_path: str) -> Dict[str, Any]:
    """
    일반 텍스트(.txt, .md 등) 문서를 일관된 포맷으로 파싱합니다.
    공공기관 문서 특성상 한글 인코딩 깨짐을 방지하기 위한 예외 처리가 포함되어 있습니다.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

    raw_text = ""
    # 1. 공공 가이드라인이나 레거시 파일의 인코딩 깨짐 방지 레이어
    encodings = ["utf-8", "cp949", "euc-kr", "utf-8-sig"]
    
    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                raw_text = f.read()
            break # 성공하면 루프 탈출
        except UnicodeDecodeError:
            continue
    else:
        # 모든 인코딩이 실패한 경우 에러 발생
        raise UnicodeError(f"지원하지 않는 파일 인코딩이거나 파일이 손상되었습니다: {file_path}")

    # 2. 기존 구축된 cleaner 엔진 적용
    cleaned_text = clean_text(raw_text)

    # 3. PDF/DOCX 파서와 동일한 딕셔너리 구조(스키마) 리턴
    return {
        "text": cleaned_text,
        "pages": [
            {
                "page_number": 1,
                "text": cleaned_text
            }
        ],
        "source_path": file_path,
        "source_name": os.path.basename(file_path),
        "document_type": "TEXT"
    }
