import re

# 중복 패턴을 제거하고 깔끔하게 정돈한 공공 표준 문서 계층 패턴
SECTION_PATTERNS = [
    r"^\d+\.\s+.+",                # 1. 제목
    r"^\d+(\.\d+)+\s+.+",          # 1.1 또는 1.1.1 제목
    r"^제\s*\d+\s*장",             # 제1장
    r"^제\s*\d+\s*절",             # 제1절
    r"^[IVX]+\.\s+.+",             # I. 로마자 제목
    r"^[가-힣]\.\s+.+",            # 가. 한글 순서 제목
    r"^[①-⑳]\s*.+",               # ① 원문자 제목
    r"^\(\d+\)\s+.+",              # (1) 괄호 숫자 제목
    r"^\[.+\]$",                   # [요구사항] 대괄호 타이틀
    r"^[■□▶◆▲▽○●-]\s*.+"         # 특수기호 불릿 스타일 제목 (- 기호 추가)
]

def is_section_line(line: str) -> bool:
    """
    [추가] 단일 라인이 섹션(장/절/타이틀)의 시작 패턴인지 명확히 판단합니다.
    processors/chunker.py 에서 아주 가볍고 안전하게 임포트하여 사용합니다.
    """
    if not line:
        return False
        
    stripped = line.strip()
    for pattern in SECTION_PATTERNS:
        if re.match(pattern, stripped):
            return True
            
    return False

def detect_section_title(text: str) -> str:
    """
    기존 로직 고도화: 입력된 텍스트 블록의 상위 10줄을 탐색하여 
    현재 컨텍스트가 어떤 섹션에 속해 있는지 타이틀 명을 반환합니다.
    """
    if not text:
        return "UNKNOWN_SECTION"

    lines = text.split("\n")

    # 상위 10줄 내에서 섹션 헤더 찾기
    for line in lines[:10]:
        stripped = line.strip()
        
        # 새로 만든 단일 라인 검증 로직 재사용
        if is_section_line(stripped):
            return stripped

    return "UNKNOWN_SECTION"
