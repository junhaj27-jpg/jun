import re
from typing import List, Dict


# =========================================================
# 🎯 산출물 분류 키워드 사전
# =========================================================
ARTIFACT_CLASSIFICATION = {

    "화면설계서": [
        "화면", "ui", "ux",
        "메뉴", "레이아웃",
        "버튼", "웹페이지",
        "모바일", "팝업",
        "컴포넌트", "시각화",
        "조회 화면", "입력 폼",
        "사용자 인터페이스",
        "도움말", "디스플레이",
        "그리드", "탭",
        "대시보드", "포털",
        "캔버스", "뷰어",
        "출력", "인터랙션"
    ],

    "엔티티 관계모형 설명": [
        "엔티티", "erd",
        "관계모형", "식별자",
        "속성", "릴레이션",
        "매핑 데이터",
        "개념 모델", "논리 모델",
        "관계도", "마이그레이션",
        "데이터 구조",
        "연관 관계", "스키마",
        "개념모델", "논리모델",
        "물리모델",
        "속성명",
        "식별키",
        "기본키",
        "외래키",
        "pk", "fk"
    ],

    "데이터베이스": [
        "데이터베이스",
        "database",
        "dbms",
        "테이블",
        "필드",
        "인덱스",
        "스토리지",
        "저장",
        "적재",
        "컬럼",
        "인코딩",
        "디코딩",
        "문자셋",
        "타입 변환",
        "저장소",
        "sql",
        "쿼리",
        "procedure",
        "프로시저",
        "데이터타입",
        "varchar",
        "number",
        "char",
        "int",
        "null",
        "트랜잭션",
        "commit",
        "rollback",
        "암호화",
        "복호화",
        "hash",
        "sha",
        "aes",
        "마스킹",
        "drm"
    ],

    "시스템아키텍처": [
        "아키텍처",
        "서버",
        "네트워크",
        "클라우드",
        "방화벽",
        "구성도",
        "인프라",
        "이중화",
        "스위치",
        "linux",
        "windows",
        "cpu",
        "메모리",
        "vcore",
        "스토리지",
        "gpu",
        "nvidia",
        "h200",
        "a100",
        "온프레미스",
        "llmops",
        "ragops",
        "웹서버",
        "was",
        "tomcat",
        "jeus",
        "웹스퀘어",
        "표준프레임워크",
        "spring",
        "egovframe",

        # 운영/모니터링
        "모니터링",
        "통합모니터링",
        "운영",
        "운영현황",
        "트래픽",
        "장애",
        "장애추적",
        "배포",
        "원격배포",
        "원격운영",
        "서비스제어",
        "통합관리",
        "백업",
        "복구",
        "로그조회",
        "설정파일"
    ],

    "통합시험시나리오": [
        "통합시험",
        "시나리오",
        "테스트",
        "시험",
        "uat",
        "검증",
        "합격기준",
        "인증",
        "오류 메시지",
        "테스트 케이스",
        "정상 동작",
        "유효성",
        "비교",
        "판단",
        "오류",
        "에러",
        "시험 시나리오",
        "단위 테스트",
        "통합 테스트",
        "시스템 테스트",
        "성능 테스트",
        "시뮬레이션",
        "보안약점",
        "취약점",
        "sql injection",
        "xss",
        "예외 처리",

        # 운영 검증
        "장애",
        "복구",
        "백업",
        "로그",
        "처리상태"
    ]
}


# =========================================================
# 🎯 비즈니스 도메인 사전
# =========================================================
BUSINESS_DOMAINS = {

    "SYSTEM_AUTH": [
        "로그인", "인증", "권한",
        "sso", "계정",
        "접근제어",
        "주민번호",
        "법인번호",
        "사업자번호",
        "외국인등록번호",
        "전화번호",
        "이메일",
        "비밀번호",
        "세션",
        "토큰",
        "oauth"
    ],

    "CORE_BUSINESS": [
        "보증", "대출",
        "정산", "이체",
        "회원", "사용자",
        "마이페이지",
        "채권", "회수",
        "리스크",
        "심사", "신용",
        "한도", "특약",
        "상품", "재정",
        "서민금융"
    ],

    "SYSTEM_INTERFACE": [
        "api", "연계",
        "인터페이스",
        "연동", "eai",
        "대외연계",
        "송수신",
        "crm", "voc",
        "대외기관",
        "전자결재",
        "상담시스템",
        "콜센터",
        "챗봇",
        "채팅상담"
    ],

    "AI_PLATFORM": [
        "llm",
        "rag",
        "agent",
        "embedding",
        "벡터",
        "파운데이션 모델",
        "생성형 ai",
        "멀티 llm",
        "prompt",
        "llmops",
        "ragops"
    ],

    "SECURITY": [
        "보안",
        "보안약점",
        "취약점",
        "시큐어코딩",
        "입력값 검증",
        "입력값검증",
        "xss",
        "sql injection",
        "명령어 삽입",
        "명령어삽입",
        "권한 상승",
        "권한상승",
        "경로조작",
        "디렉토리",
        "리소스",
        "검증절차",
        "예외처리",
        "세션통제"
    ]
}


# =========================================================
# 🎯 단일 키워드 허용 (precision 보정)
# =========================================================
HIGH_PRIORITY_SINGLE_MATCH = {

    "시스템아키텍처": [
        "gpu",
        "ragops",
        "llmops",
        "클라우드",
        "was",
        "tomcat",
        "jeus"
    ],

    "엔티티 관계모형 설명": [
        "erd",
        "pk",
        "fk"
    ]
}


# =========================================================
# 🎯 텍스트 정규화
# =========================================================
def _normalize_text(text: str) -> str:

    text = text.lower()

    text = re.sub(r"\s+", "", text)

    text = re.sub(r"[^\w가-힣]", "", text)

    return text


# =========================================================
# 🎯 메인 함수
# =========================================================
def detect_requirement_domain(text: str) -> Dict[str, List[str]]:

    result = {
        "target_artifacts": [],
        "business_domains": []
    }

    # -------------------------------------------------
    # 빈 값 방어
    # -------------------------------------------------
    if not text:
        result["target_artifacts"].append("일반참고문서")
        result["business_domains"].append("GENERAL")
        return result

    # -------------------------------------------------
    # 텍스트 정규화
    # -------------------------------------------------
    lower_text = text.lower()

    clean_text_for_match = _normalize_text(text)

    # -------------------------------------------------
    # [1] 산출물 매핑
    # -------------------------------------------------
    for artifact, keywords in ARTIFACT_CLASSIFICATION.items():

        match_score = 0
        matched_keywords = []

        for keyword in keywords:

            keyword_lower = keyword.lower()

            keyword_clean = _normalize_text(keyword)

            if (
                keyword_lower in lower_text
                or keyword_clean in clean_text_for_match
            ):
                match_score += 1
                matched_keywords.append(keyword)

        # 일반 규칙
        if match_score >= 2:
            result["target_artifacts"].append(artifact)

        # 중요 키워드 단일 허용
        elif artifact in HIGH_PRIORITY_SINGLE_MATCH:

            for matched_keyword in matched_keywords:

                if matched_keyword in HIGH_PRIORITY_SINGLE_MATCH[artifact]:
                    result["target_artifacts"].append(artifact)
                    break

    # -------------------------------------------------
    # [2] 비즈니스 도메인 매핑
    # -------------------------------------------------
    for domain, keywords in BUSINESS_DOMAINS.items():

        for keyword in keywords:

            keyword_lower = keyword.lower()

            keyword_clean = _normalize_text(keyword)

            if (
                keyword_lower in lower_text
                or keyword_clean in clean_text_for_match
            ):
                result["business_domains"].append(domain)
                break

    # -------------------------------------------------
    # [3] 폴백 처리
    # -------------------------------------------------
    if not result["target_artifacts"]:
        result["target_artifacts"].append("일반참고문서")

    if not result["business_domains"]:
        result["business_domains"].append("GENERAL")

    # -------------------------------------------------
    # [4] 중복 제거
    # -------------------------------------------------
    result["target_artifacts"] = sorted(
        list(set(result["target_artifacts"]))
    )

    result["business_domains"] = sorted(
        list(set(result["business_domains"]))
    )

    return result