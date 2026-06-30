"""테이블 타입별 컬럼을 설계합니다."""

from typing import Any


COMMON_COLUMNS = (
    ("crt_dt", "TIMESTAMP", False, "생성 일시", "", []),
    ("creatr_sn", "BIGINT", True, "생성자 일련번호", "", []),
    ("udt_dt", "TIMESTAMP", True, "수정 일시", "", []),
    ("updusr_sn", "BIGINT", True, "수정자 일련번호", "", []),
    ("del_yn", "CHAR(1)", False, "삭제 여부", "N", ["Y/N"]),
)


def design_columns(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tables = []
    for index, candidate in enumerate(candidates, start=1):
        table = dict(candidate)
        table["table_id"] = str(table.get("table_id") or f"TABLE-{index:03d}")
        table["entity_id"] = str(table.get("entity_id") or f"ENTITY-{index:03d}")
        table["description"] = _description(table)
        table["logical_name"] = table["table_korean_name"]
        table["physical_name"] = table["table_name"]
        columns = _type_columns(table)
        columns = _add_common_columns(columns, table["table_type"])
        table["columns"] = [_column(col_index, *item) for col_index, item in enumerate(columns, start=1)]
        tables.append(table)
    return tables


def _type_columns(table: dict[str, Any]) -> list[tuple[str, str, bool, str, Any, list[str]]]:
    table_name = str(table["table_name"])
    table_type = str(table["table_type"])
    base = table_name.removeprefix("tbl_")
    pk_name = _pk_name(table_name)
    if table_type == "FILE":
        return [
            (pk_name, "BIGINT", False, "파일 일련번호", "", ["PK", "AUTO_INCREMENT"]),
            ("document_sn", "BIGINT", False, "문서 일련번호", "", ["FK"]),
            ("file_nm", "VARCHAR(300)", False, "파일명", "", []),
            ("file_path", "VARCHAR(1000)", False, "파일 경로", "", []),
            ("file_ext", "VARCHAR(20)", True, "파일 확장자", "", []),
            ("mime_type", "VARCHAR(100)", True, "MIME 타입", "", []),
            ("file_size", "BIGINT", True, "파일 크기", "", []),
            ("storage_type_cd", "VARCHAR(30)", True, "저장소 구분 코드", "", []),
        ]
    if table_type == "APPROVAL":
        return [
            ("approval_sn", "BIGINT", False, "승인 일련번호", "", ["PK", "AUTO_INCREMENT"]),
            ("target_type", "VARCHAR(50)", False, "승인 대상 유형", "", []),
            ("target_sn", "BIGINT", False, "승인 대상 일련번호", "", []),
            ("requester_sn", "BIGINT", False, "요청자 일련번호", "", ["FK"]),
            ("approver_sn", "BIGINT", True, "승인자 일련번호", "", ["FK"]),
            ("approval_status_cd", "VARCHAR(30)", False, "승인 상태 코드", "PENDING", ["PENDING/APPROVED/REJECTED"]),
            ("request_reason", "TEXT", True, "요청 사유", "", []),
            ("reject_reason", "TEXT", True, "반려 사유", "", []),
            ("requested_at", "TIMESTAMP", False, "요청 일시", "", []),
            ("approved_at", "TIMESTAMP", True, "승인 일시", "", []),
        ]
    if table_type in {"JOB", "JOB_STEP"}:
        pk = "job_step_sn" if table_type == "JOB_STEP" else "job_sn"
        columns = [
            (pk, "BIGINT", False, f"{table['table_korean_name']} 일련번호", "", ["PK", "AUTO_INCREMENT"]),
        ]
        if table_type == "JOB_STEP":
            columns.append(("job_sn", "BIGINT", False, "작업 일련번호", "", ["FK"]))
            columns.append(("step_no", "INTEGER", False, "단계 번호", "", []))
            columns.append(("step_nm", "VARCHAR(200)", False, "단계명", "", []))
        else:
            columns.append(("job_nm", "VARCHAR(200)", False, "작업명", "", []))
        columns.extend(
            [
                ("job_status_cd", "VARCHAR(30)", False, "작업 상태 코드", "PENDING", ["PENDING/PROCESSING/DONE/FAILED/CANCELED"]),
                ("started_at", "TIMESTAMP", True, "시작 일시", "", []),
                ("ended_at", "TIMESTAMP", True, "종료 일시", "", []),
                ("error_message", "TEXT", True, "오류 메시지", "", []),
            ]
        )
        return columns
    if table_type == "INDEX":
        return [
            ("embedding_sn", "BIGINT", False, "임베딩 일련번호", "", ["PK", "AUTO_INCREMENT"]),
            ("chunk_sn", "BIGINT", False, "청크 일련번호", "", ["FK"]),
            ("vector_db", "VARCHAR(100)", False, "벡터DB 명", "", []),
            ("collection_name", "VARCHAR(200)", False, "컬렉션명", "", []),
            ("point_id", "VARCHAR(200)", False, "포인트 ID", "", []),
            ("embedding_model_sn", "BIGINT", True, "임베딩 모델 일련번호", "", ["FK"]),
            ("indexed_at", "TIMESTAMP", False, "색인 일시", "", []),
        ]
    if table_type == "DETAIL" and "chunk" in table_name:
        return [
            ("chunk_sn", "BIGINT", False, "청크 일련번호", "", ["PK", "AUTO_INCREMENT"]),
            ("document_sn", "BIGINT", False, "문서 일련번호", "", ["FK"]),
            ("chunk_no", "INTEGER", False, "청크 번호", "", []),
            ("chunk_text", "TEXT", False, "청크 내용", "", []),
            ("page_no", "INTEGER", True, "페이지 번호", "", []),
            ("token_count", "INTEGER", True, "토큰 수", "", []),
            ("metadata_json", "TEXT", True, "메타데이터 JSON", "", []),
        ]
    if table_type == "VERSION":
        root = base.removesuffix("_version")
        return [
            (f"{root}_ver_sn", "BIGINT", False, "버전 일련번호", "", ["PK", "AUTO_INCREMENT"]),
            (_pk_name(f"tbl_{root}"), "BIGINT", False, f"{table['table_korean_name']} 원본 일련번호", "", ["FK"]),
            ("version_no", "VARCHAR(30)", False, "버전 번호", "", []),
            ("active_yn", "CHAR(1)", False, "활성 여부", "Y", ["Y/N"]),
            ("change_summary", "TEXT", True, "변경 요약", "", []),
            ("deployed_at", "TIMESTAMP", True, "배포 일시", "", []),
        ]
    if table_type in {"LOG", "HISTORY"}:
        return [
            (pk_name, "BIGINT", False, f"{table['table_korean_name']} 일련번호", "", ["PK", "AUTO_INCREMENT"]),
            ("target_type", "VARCHAR(50)", True, "대상 유형", "", []),
            ("target_sn", "BIGINT", True, "대상 일련번호", "", []),
            ("event_type_cd", "VARCHAR(50)", False, "이벤트 유형 코드", "", []),
            ("occurred_at", "TIMESTAMP", False, "발생 일시", "", []),
            ("request_id", "VARCHAR(100)", True, "요청 ID", "", []),
            ("trace_id", "VARCHAR(100)", True, "추적 ID", "", []),
            ("error_message", "TEXT", True, "오류 메시지", "", []),
        ]
    if table_type == "MAPPING":
        tokens = [token for token in base.split("_") if token]
        left = tokens[0] if tokens else "source"
        right = tokens[1] if len(tokens) > 1 else "target"
        return [
            (f"{base}_sn", "BIGINT", False, f"{table['table_korean_name']} 일련번호", "", ["PK", "AUTO_INCREMENT"]),
            (f"{left}_sn", "BIGINT", False, f"{left} 일련번호", "", ["FK"]),
            (f"{right}_sn", "BIGINT", False, f"{right} 일련번호", "", ["FK"]),
        ]
    return [
        (pk_name, "BIGINT", False, f"{table['table_korean_name']} 일련번호", "", ["PK", "AUTO_INCREMENT"]),
        (f"{base}_nm", "VARCHAR(200)", False, f"{table['table_korean_name']}명", "", []),
        (f"{base}_cn", "TEXT", True, f"{table['table_korean_name']} 내용", "", []),
        (f"{base}_status_cd", "VARCHAR(30)", False, f"{table['table_korean_name']} 상태 코드", "ACTIVE", ["ACTIVE/INACTIVE"]),
    ]


def _add_common_columns(
    columns: list[tuple[str, str, bool, str, Any, list[str]]],
    table_type: str,
) -> list[tuple[str, str, bool, str, Any, list[str]]]:
    if table_type in {"LOG", "HISTORY"}:
        return columns
    names = {column[0] for column in columns}
    return [*columns, *(column for column in COMMON_COLUMNS if column[0] not in names)]


def _column(index: int, name: str, data_type: str, nullable: bool, description: str, default: Any, constraints: list[str]) -> dict[str, Any]:
    type_name, length = _split_type(data_type)
    return {
        "column_id": f"COL-{index:03d}",
        "column_name": name,
        "physical_name": name,
        "logical_name": description,
        "data_type": data_type,
        "length": length,
        "pk": "PK" in constraints,
        "fk": "FK" in constraints,
        "nullable": nullable,
        "default": default or "",
        "constraints": constraints,
        "description": description,
        "type": type_name,
    }


def _pk_name(table_name: str) -> str:
    base = table_name.removeprefix("tbl_")
    if base.endswith("_file"):
        return "file_sn"
    if base.endswith("_approval"):
        return "approval_sn"
    return f"{base}_sn"


def _description(table: dict[str, Any]) -> str:
    name = table.get("table_korean_name") or table.get("table_name")
    return f"{name} 정보를 관리한다."


def _split_type(data_type: str) -> tuple[str, str]:
    if "(" not in data_type:
        return data_type, ""
    return data_type.split("(", 1)[0], data_type.split("(", 1)[1].rstrip(")")
