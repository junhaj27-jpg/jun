"""최종 테이블 목록에서 PK/FK 관계를 추론합니다."""

import re
from typing import Any


def infer_relationships(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_table = {table["table_name"]: table for table in tables}
    pk_by_table = {
        table["table_name"]: _pk_column(table)
        for table in tables
    }
    pk_owner = {
        pk: table_name
        for table_name, pk in pk_by_table.items()
        if pk
    }
    relationships: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for table in tables:
        for column in table.get("columns", []):
            column_name = str(column.get("column_name") or "")
            parent_table = pk_owner.get(column_name)
            parent_column = column_name
            if parent_table is None and _looks_like_fk(column):
                candidates = rank_parent_candidates(tables, str(table["table_name"]), column)
                if _can_auto_select(candidates):
                    parent_table = str(candidates[0]["parent_table"])
                    parent_column = str(candidates[0]["parent_column"])
            if parent_table is None:
                continue
            child_table = table["table_name"]
            if parent_table == child_table:
                continue
            parent_column = parent_column or pk_by_table.get(parent_table) or column_name
            key = (parent_table, parent_column, child_table, column_name)
            if key in seen or parent_table not in by_table:
                continue
            seen.add(key)
            relationships.append(
                {
                    "relationship_id": f"REL-{len(relationships) + 1:03d}",
                    "from_table": child_table,
                    "from_column": column_name,
                    "to_table": parent_table,
                    "to_column": parent_column,
                    "parent_table": parent_table,
                    "parent_column": parent_column,
                    "child_table": child_table,
                    "child_column": column_name,
                    "relationship_type": "N:1",
                    "description": f"{child_table}는 {parent_table}를 참조한다.",
                }
            )
    return relationships


def rank_parent_candidates(
    tables: list[dict[str, Any]],
    child_table: str,
    fk_column: dict[str, Any],
) -> list[dict[str, Any]]:
    """물리명·논리명·타입 기반으로 기존 PK 후보만 순위화합니다."""

    fk_name = str(fk_column.get("column_name") or fk_column.get("physical_name") or "")
    fk_stem = _identifier_stem(fk_name)
    fk_tokens = _semantic_tokens(
        fk_stem,
        fk_column.get("attribute_name"),
        fk_column.get("logical_name"),
        fk_column.get("column_logical_name"),
        fk_column.get("description"),
    )
    fk_type = _normalized_type(fk_column)
    candidates = []
    for table in tables:
        table_name = str(table.get("table_name") or table.get("physical_name") or "")
        if not table_name or table_name == child_table:
            continue
        pk_column = _pk_column_object(table)
        if pk_column is None:
            continue
        pk_name = str(pk_column.get("column_name") or pk_column.get("physical_name") or "")
        table_base = _identifier_stem(table_name.removeprefix("tbl_"))
        pk_stem = _identifier_stem(pk_name)
        parent_tokens = _semantic_tokens(
            table_base,
            pk_stem,
            table.get("entity_name"),
            table.get("logical_name"),
            table.get("table_logical_name"),
        )
        score = 0
        reasons = []
        if fk_name == pk_name:
            score += 100
            reasons.append("physical_key_exact")
        if fk_stem and fk_stem in {table_base, pk_stem}:
            score += 85
            reasons.append("identifier_stem_exact")
        overlap = fk_tokens & parent_tokens
        if overlap:
            ratio = len(overlap) / max(1, len(fk_tokens))
            score += int(55 * ratio)
            reasons.append(f"semantic_tokens:{','.join(sorted(overlap))}")
        if fk_type and fk_type == _normalized_type(pk_column):
            score += 10
            reasons.append("data_type_compatible")
        structural_tokens = parent_tokens & _STRUCTURAL_TOKENS
        if structural_tokens and not (fk_tokens & structural_tokens):
            score -= 30
            reasons.append(
                f"structural_variant_penalty:{','.join(sorted(structural_tokens))}"
            )
        # 타입 일치만으로는 부모 후보 근거가 되지 않습니다.
        if score <= 10:
            continue
        candidates.append(
            {
                "parent_table": table_name,
                "parent_column": pk_name,
                "parent_entity_name": table.get("entity_name") or table.get("logical_name"),
                "parent_pk_logical_name": pk_column.get("attribute_name")
                or pk_column.get("logical_name")
                or pk_column.get("column_logical_name"),
                "data_type": pk_column.get("data_type"),
                "score": score,
                "reasons": reasons,
            }
        )
    return sorted(candidates, key=lambda item: (-int(item["score"]), str(item["parent_table"])))


def _can_auto_select(candidates: list[dict[str, Any]]) -> bool:
    if not candidates or int(candidates[0]["score"]) < 60:
        return False
    return len(candidates) == 1 or int(candidates[0]["score"]) - int(candidates[1]["score"]) >= 20


_IDENTIFIER_ALIASES = {
    "organization": "org",
    "organisation": "org",
    "department": "dept",
    "document": "docs",
    "doc": "docs",
}


def _alias_owner_map(tables: list[dict[str, Any]]) -> dict[str, str]:
    candidates: dict[str, list[str]] = {}
    for table in tables:
        table_name = str(table.get("table_name") or "")
        base = table_name.removeprefix("tbl_")
        aliases = {base, _canonical_identifier(base)}
        for alias, canonical in _IDENTIFIER_ALIASES.items():
            if canonical in aliases:
                aliases.add(alias)
        for alias in aliases:
            candidates.setdefault(alias, []).append(table_name)
    return {
        alias: owners[0]
        for alias, owners in candidates.items()
        if len(set(owners)) == 1
    }


def _looks_like_fk(column: dict[str, Any]) -> bool:
    name = str(column.get("column_name") or column.get("physical_name") or "")
    constraints = {str(item).upper() for item in column.get("constraints") or []}
    return bool(column.get("fk") or "FK" in constraints or name.endswith(("_sn", "_id")))


def _identifier_stem(value: str) -> str:
    stem = str(value or "").lower()
    for suffix in ("_sn", "_id"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return _canonical_identifier(stem)


def _canonical_identifier(value: str) -> str:
    return _IDENTIFIER_ALIASES.get(value, value)


def _pk_column(table: dict[str, Any]) -> str:
    column = _pk_column_object(table)
    if column is not None:
        return str(column.get("column_name") or column.get("physical_name") or "")
    return ""


def _pk_column_object(table: dict[str, Any]) -> dict[str, Any] | None:
    for column in table.get("columns", []):
        if not isinstance(column, dict):
            continue
        value = column.get("pk") or column.get("is_pk")
        marked = value.strip().upper() in {"Y", "YES", "TRUE", "1", "PK"} if isinstance(value, str) else bool(value)
        constraints = {str(item).upper() for item in column.get("constraints", [])}
        if marked or bool(constraints & {"PK", "PRIMARY KEY"}):
            return column
    return None


_SEMANTIC_ALIASES = {
    "organization": "org",
    "organisation": "org",
    "부서": "dept",
    "조직": "org",
    "문서": "docs",
    "document": "docs",
    "doc": "docs",
    "사용자": "actor",
    "회원": "actor",
    "담당자": "actor",
    "요청자": "actor",
    "신청자": "actor",
    "승인자": "actor",
    "결재자": "actor",
    "등록자": "actor",
    "수정자": "actor",
    "소유자": "actor",
    "user": "actor",
    "member": "actor",
    "requester": "actor",
    "applicant": "actor",
    "approver": "actor",
    "creator": "actor",
    "updater": "actor",
    "owner": "actor",
    "assignee": "actor",
}

_STRUCTURAL_TOKENS = {
    "version",
    "버전",
    "history",
    "hist",
    "이력",
    "log",
    "로그",
    "detail",
    "상세",
    "step",
    "단계",
}


def _semantic_tokens(*values: Any) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        text = str(value or "").lower()
        for raw in re.findall(r"[0-9a-z가-힣]+", text):
            normalized = _SEMANTIC_ALIASES.get(raw, _canonical_identifier(raw))
            if normalized not in {"sn", "id", "pk", "fk", "번호", "일련번호", "식별자"}:
                tokens.add(normalized)
    return tokens


def _normalized_type(column: dict[str, Any]) -> str:
    value = str(column.get("data_type") or column.get("type_and_length") or "").upper()
    return re.sub(r"\s|\(.*", "", value)
