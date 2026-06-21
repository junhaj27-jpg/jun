"""범용 객체/이벤트 기반 테이블 후보를 생성합니다."""

from typing import Any

from agents.data_structure_design.processors.column_standardizer import table_name


GENERIC_TABLES = {
    "문서": ("tbl_document", "문서", "MASTER", "문서 메타데이터 관리"),
    "파일": ("tbl_document_file", "문서파일", "FILE", "실제 파일 경로 및 파일 속성 관리"),
    "사용자": ("tbl_user", "사용자", "MASTER", "사용자 정보 관리"),
    "고객": ("tbl_customer", "고객", "MASTER", "고객 정보 관리"),
    "부서": ("tbl_dept", "부서", "MASTER", "부서 정보 관리"),
    "조직": ("tbl_org", "조직", "MASTER", "조직 정보 관리"),
    "권한": ("tbl_role", "권한", "MASTER", "권한 정보 관리"),
    "메뉴": ("tbl_menu", "메뉴", "MASTER", "메뉴 정보 관리"),
    "코드": ("tbl_code", "코드", "CODE", "공통 코드 관리"),
    "설정": ("tbl_config", "설정", "CONFIG", "업무/시스템 설정 관리"),
    "승인": ("tbl_approval", "승인", "APPROVAL", "신청/승인/반려 흐름 관리"),
    "로그": ("tbl_audit_log", "감사로그", "LOG", "감사 추적 로그 관리"),
    "이력": ("tbl_status_hist", "상태이력", "HISTORY", "상태 변경 이력 관리"),
    "작업": ("tbl_job", "작업", "JOB", "비동기 처리 작업 관리"),
    "단계": ("tbl_job_step", "작업단계", "JOB_STEP", "작업 단계별 상태 관리"),
    "청크": ("tbl_document_chunk", "문서청크", "DETAIL", "문서 분할 내용 관리"),
    "임베딩": ("tbl_embedding_index", "임베딩색인", "INDEX", "임베딩 벡터 색인 관리"),
    "RAG": ("tbl_rag_job", "RAG작업", "JOB", "RAG 처리 작업 관리"),
    "AI 모델": ("tbl_ai_model", "AI모델", "MASTER", "AI 모델 설정 관리"),
    "Agent": ("tbl_agent", "Agent", "MASTER", "Agent 설정 관리"),
    "프롬프트": ("tbl_prompt_template", "프롬프트템플릿", "MASTER", "프롬프트 템플릿 관리"),
}

def generate_table_candidates(
    requirements: list[dict[str, Any]],
    objects: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    for obj in objects:
        table_name_value, korean_name, table_type, reason = _table_for_object(obj)
        _merge_candidate(candidates, table_name_value, korean_name, table_type, reason, [obj["requirement_id"]])
        if obj["name"] == "RAG":
            _merge_candidate(
                candidates,
                "tbl_rag_job_step",
                "RAG작업단계",
                "JOB_STEP",
                "RAG 작업 단계별 처리 상태 관리",
                [obj["requirement_id"]],
            )
        if obj["name"] == "문서":
            _merge_candidate(
                candidates,
                "tbl_document_file",
                "문서파일",
                "FILE",
                "문서 메타데이터와 실제 파일 정보를 분리 관리",
                [obj["requirement_id"]],
            )

    for requirement in requirements:
        text = f"{requirement['requirement_name']}\n{requirement['detail']}"
        source_ids = [requirement["requirement_id"]]
        if _has_any(text, ("버전관리", "변경이력", "배포이력", "이전 버전", "활성 버전", "수정 전후 비교")):
            _add_version_candidates(candidates, objects, requirement["requirement_id"])
        if _has_any(text, ("N:M", "여러 권한", "여러 메뉴", "태그", "ACL")):
            _add_mapping_candidates(candidates, text, source_ids)

    for event in events:
        if any(name in event["business_events"] for name in ("실행", "배치", "스케줄", "전처리", "수집", "적재", "처리")):
            _merge_candidate(candidates, "tbl_job", "작업", "JOB", "비동기 처리 작업 관리", [event["requirement_id"]])
            _merge_candidate(candidates, "tbl_job_step", "작업단계", "JOB_STEP", "작업 단계별 상태 관리", [event["requirement_id"]])

    return list(candidates.values())


def _table_for_object(obj: dict[str, Any]) -> tuple[str, str, str, str]:
    name = str(obj["name"])
    if name in GENERIC_TABLES:
        return GENERIC_TABLES[name]
    table_name_value = table_name(name)
    return table_name_value, name, str(obj.get("object_type") or "MASTER"), f"{name} 정보 관리"


def _add_version_candidates(
    candidates: dict[str, dict[str, Any]],
    objects: list[dict[str, Any]],
    requirement_id: str,
) -> None:
    for obj in objects:
        if obj["requirement_id"] != requirement_id:
            continue
        table_name_value, korean_name, _, _ = _table_for_object(obj)
        base = table_name_value.removeprefix("tbl_")
        _merge_candidate(
            candidates,
            f"tbl_{base}_version",
            f"{korean_name}버전",
            "VERSION",
            f"{korean_name} 버전 이력 관리",
            [requirement_id],
        )


def _add_mapping_candidates(candidates: dict[str, dict[str, Any]], text: str, source_ids: list[str]) -> None:
    pairs = (
        ("사용자", "권한", "tbl_user_role", "사용자권한"),
        ("권한", "메뉴", "tbl_role_menu", "권한메뉴"),
        ("문서", "태그", "tbl_document_tag_map", "문서태그"),
    )
    for left, right, table_name_value, korean_name in pairs:
        if left in text and right in text:
            _merge_candidate(candidates, table_name_value, korean_name, "MAPPING", f"{left}와 {right}의 N:M 매핑 관리", source_ids)


def _merge_candidate(
    candidates: dict[str, dict[str, Any]],
    table_name_value: str,
    korean_name: str,
    table_type: str,
    reason: str,
    source_requirement_ids: list[str],
) -> None:
    current = candidates.get(table_name_value)
    if current is None:
        candidates[table_name_value] = {
            "table_name": table_name_value,
            "table_korean_name": korean_name,
            "table_type": table_type,
            "reason": reason,
            "source_requirement_ids": list(dict.fromkeys(source_requirement_ids)),
        }
        return
    current["source_requirement_ids"] = list(
        dict.fromkeys([*current.get("source_requirement_ids", []), *source_requirement_ids])
    )


def _has_any(text: str, keywords: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(keyword.lower() in lower for keyword in keywords)
