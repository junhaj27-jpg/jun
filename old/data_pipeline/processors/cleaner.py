import re

def auto_mask_institutions(text: str) -> str:
    """
    [패턴 자동화 엔진] 특정 기업명을 지정하지 않고, 
    한국어 기관/기업/법인명 특유의 접미사 패턴을 역추적하여 자동으로 마스킹합니다.
    """
    if not text:
        return ""
        
    # 💡 대한민국 공공기관, 금융기관, 기업체 명칭의 표준 접미사 정규식 매트릭스
    # 예: 기술보증기금, 서민금융진흥원, 신용회복위원회, 한국전기안전공사, 오픈소스주식회사 등 일괄 매칭
    regex_patterns = [
        # 1. 3~7글자 단어 뒤에 기금/원/위원회/공사/청/본부/연구소 등이 붙는 패턴
        r"[가-힣]{2,7}(기금|진흥원|위원회|공사|연구소|센터|정보원|중앙회|관리원| 협회)",
        
        # 2. 주식회사 명칭 및 괄호 법인 기호 처리
        r"주식회사\s*[가-힣A-Za-z0-9]{2,10}",
        r"[가-힣A-Za-z0-9]{2,10}\s*\(주\)",
        
        # 3. 일반적인 기업 접미사 (~테크, ~소프트, ~시스템즈 등 정보화 사업 수행사 타깃)
        r"[가-힣A-Za-z0-9]{2,8}(테크|소프트|시스템즈|네트웍스|아이앤씨|씨엔씨)"
    ]
    
    # 발견된 모든 가변 기관명을 일괄 안전하게 [기관명] 가슴 레이블로 치환
    for pattern in regex_patterns:
        text = re.sub(pattern, "[기관명]", text)
        
    return text


def remove_table_of_contents(text: str) -> str:
    """
    문서 텍스트 전체를 검사하여 점선(··· 또는 ...)이나 
    목차 특유의 페이지 번호 패턴이 있는 줄을 완벽하게 제거합니다.
    """
    if not text:
        return ""
        
    lines = text.split("\n")
    clean_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        # 1. 점선 패턴 감지 (· 또는 .이 3개 이상 연속된 경우)
        if len(re.findall(r'[·\.]{3,}', stripped)) > 0:
            continue
            
        # 2. 공공기관 목차 특유의 '가이드라인  12' 처럼 공백 뒤 숫자로 끝나는 긴 라인 감지
        if re.search(r'\s+\d+$', stripped) and len(stripped) > 15:
            # 탭 문자나 연속된 공백, 혹은 문장 부호가 숫자로 이어지면 목차로 간주
            if re.search(r'(\s{2,})|([·\.]{2,})', stripped):
                continue
                
        clean_lines.append(line)
        
    return "\n".join(clean_lines)

def clean_text(text: str) -> str:
    if not text:
        return ""
    
    # 1. 깨진 공백 유니코드(\xa0) 및 미세 특수문자 선제 정제
    text = remove_table_of_contents(text)

    text = text.replace("\xa0", " ")
    
    # 2. 🎯 [자동화 진화] 하드코딩 없이 문맥 접미사 패턴으로 기업/기관명 일괄 자동 마스킹
    text = auto_mask_institutions(text)
    
    lines = text.split("\n")
    cleaned_lines = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            continue
        
        if re.match(r"^\d+\s*\|?\s*$", stripped): continue
        # 구분선 제거
        if re.match(r"^[-=_─★☆■□▲△▼▽◆◇●○]{3,}$", stripped):
            continue
        
        # 본문 페이지 번호 제거
        if re.match(
            r"^[-=\[\]\s]*\d+[-=\[\]\s]*$|^p(g)?\.\s*\d+$", 
            stripped, 
            flags=re.IGNORECASE
        ):
            continue

        # 연속된 다중 공백을 단일 공백으로 치환
        processed = re.sub(r"\s{2,}", " ", stripped)
        cleaned_lines.append(processed)
        
    result = "\n".join(cleaned_lines)
    return result.strip()
