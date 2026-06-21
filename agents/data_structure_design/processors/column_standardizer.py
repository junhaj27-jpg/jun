# 데이터베이스 컬럼명을 표준 명명 규칙으로 변환합니다.

import re
from hashlib import sha1


TERM_MAP = {
    "사용자": "user",
    "유저": "user",
    "회원": "member",
    "권한": "role",
    "역할": "role",
    "문서": "docs",
    "산출물": "docs",
    "파일": "file",
    "첨부": "attach",
    "승인": "approval",
    "결재": "approval",
    "통계": "stats",
    "로그인": "login",
    "인증": "auth",
    "계정": "account",
    "관리": "management",
    "이력": "history",
    "상담": "counsel",
    "신청": "request",
    "고객": "customer",
    "상품": "product",
    "정책": "policy",
    "설정": "config",
    "알림": "notice",
    "메시지": "message",
    "화면": "screen",
    "데이터": "data",
    "조직": "org",
    "부서": "dept",
    "태그": "tag",
    "청크": "chunk",
    "임베딩": "embedding",
    "에이전트": "agent",
    "프롬프트": "prompt",
    "모델": "model",
    "컬렉션": "collection",
    "번호": "sn",
    "일련번호": "sn",
    "아이디": "id",
    "명": "nm",
    "이름": "nm",
    "내용": "cn",
    "상태": "status",
    "코드": "cd",
    "일시": "dt",
    "일자": "date",
    "생성": "create",
    "수정": "update",
    "삭제": "delete",
}


def standardize_name(value: str, *, fallback: str = "item") -> str:
    translated = str(value or "")
    for korean, english in TERM_MAP.items():
        translated = translated.replace(korean, f" {english} ")
    normalized = re.sub(r"[^0-9A-Za-z]+", "_", translated).strip("_").lower()
    normalized = re.sub(r"_+", "_", normalized)
    if not normalized:
        normalized = fallback
    if normalized[0].isdigit():
        normalized = f"{fallback}_{normalized}"
    return normalized


def table_name(entity_name: str) -> str:
    name = standardize_name(entity_name, fallback="entity")
    if name == "entity" and str(entity_name or "").strip():
        digest = sha1(str(entity_name).encode("utf-8")).hexdigest()[:8]
        name = f"unresolved_{digest}"
    if name == "tbl":
        name = "entity"
    return name if name.startswith("tbl_") else f"tbl_{name}"


def primary_key_name(entity_name: str) -> str:
    name = standardize_name(entity_name, fallback="entity")
    if name.startswith("tbl_"):
        name = name.removeprefix("tbl_")
    return f"{name}_sn"
