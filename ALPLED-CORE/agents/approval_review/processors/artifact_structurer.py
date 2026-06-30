from __future__ import annotations

import re
from typing import Any

from agents.document_merge.processors.artifact_parser import artifact_items
from config.constants import normalize_docs_cd


def structure_artifact_content(docs_cd: str, content: Any) -> dict[str, Any]:
    """산출물 내용을 업무 식별자가 있는 비교용 JSON으로 정규화합니다."""

    normalized = normalize_docs_cd(docs_cd)
    normalized = "UI" if normalized == "INTERFACE" else normalized
    if isinstance(content, (dict, list)) and not _is_document_content(content):
        return _normalize_json_content(normalized, content)
    if not isinstance(content, dict):
        raise ValueError(f"{normalized} 산출물 내용을 구조화할 수 없습니다.")

    tables = content.get("tables") if isinstance(content.get("tables"), list) else []
    paragraphs = content.get("paragraphs") or content.get("pages") or []
    parser = {
        "SRS": _structure_srs,
        "UI": _structure_interface,
        "ERD": _structure_erd,
        "DB": _structure_db,
        "ARCH": _structure_arch,
        "TS": _structure_ts,
    }.get(normalized)
    if parser is None:
        raise ValueError(f"지원하지 않는 산출물 코드입니다: {docs_cd}")

    structured = parser(tables, paragraphs)
    if not _has_business_items(structured):
        raise ValueError(f"{normalized} DOCX에서 비교 가능한 업무 JSON을 추출하지 못했습니다.")
    return structured


def _normalize_json_content(docs_cd: str, content: Any) -> dict[str, Any]:
    if isinstance(content, list):
        return {_root_key(docs_cd): content}
    if not isinstance(content, dict):
        return {_root_key(docs_cd): [content]}
    content = _unwrap_json_content(content)
    normalizer = {
        "SRS": _normalize_srs_json,
        "UI": _normalize_interface_json,
        "ERD": _normalize_erd_json,
        "DB": _normalize_db_json,
        "ARCH": _normalize_arch_json,
        "TS": _normalize_ts_json,
    }.get(docs_cd)
    if normalizer is None:
        return {_root_key(docs_cd): [content]}
    return normalizer(content)


def _unwrap_json_content(content: dict[str, Any]) -> dict[str, Any]:
    current = content
    for _ in range(4):
        nested = next(
            (
                current.get(key)
                for key in ("final_document_json", "result", "content")
                if isinstance(current.get(key), dict)
            ),
            None,
        )
        if nested is None:
            break
        current = nested
    return current


def _normalize_srs_json(content: dict[str, Any]) -> dict[str, Any]:
    requirements = _find_list(
        content,
        "requirements",
        "requirement_json_list",
        "final_requirement_json_list",
        "integrated_requirement_json_list",
    )
    return {"requirements": requirements or _shared_artifact_items(content)}


def _normalize_interface_json(content: dict[str, Any]) -> dict[str, Any]:
    screens = _find_list(
        content,
        "screens",
        "interface_json_list",
        "reference_interface_json_list",
        "interface_image_analysis_json_list",
    )
    return {"screens": screens or _shared_artifact_items(content)}


def _normalize_erd_json(content: dict[str, Any]) -> dict[str, Any]:
    document = _find_dict(content, "erd_entity_json") or content
    result: dict[str, Any] = {
        "entities": _find_list(document, "tables", "entities", "erd_entity_json_list")
        or _shared_artifact_items(document),
    }
    relationships = _find_list(document, "relationships", "relations")
    if relationships is not None:
        result["relationships"] = relationships
    return result


def _normalize_db_json(content: dict[str, Any]) -> dict[str, Any]:
    document = _find_dict(content, "db_design_json") or content
    result: dict[str, Any] = {
        "tables": _find_list(document, "tables", "entities", "db_table_json_list")
        or _shared_artifact_items(document),
    }
    for output_key, aliases in {
        "relationships": ("relationships", "relations"),
        "indexes": ("indexes", "index_json_list"),
        "constraints": ("constraints", "constraint_json_list"),
    }.items():
        value = _find_list(document, *aliases)
        if value is not None:
            result[output_key] = value
    return result


def _normalize_arch_json(content: dict[str, Any]) -> dict[str, Any]:
    structure = _find_dict(content, "architecture_structure_json") or content
    document = _find_dict(content, "architecture_document_json") or {}
    result: dict[str, Any] = {
        "components": _find_list(structure, "components") or [],
    }
    list_fields = {
        "relations": ("relations", "edges"),
        "layers": ("layers", "subgraphs"),
        "drivers": ("drivers",),
    }
    for output_key, aliases in list_fields.items():
        value = _find_list(structure, *aliases)
        if value is not None:
            result[output_key] = value
    for output_key, aliases in {
        "deployment_environment": ("deployment_environment", "deployment"),
    }.items():
        value = _find_value(structure, *aliases)
        if value is not None:
            result[output_key] = value
    for key in (
        "overview",
        "security",
        "performance",
        "operation",
        "integration",
        "architecture_config_reflected",
    ):
        if key in structure:
            result[key] = structure[key]
    requirement_implementations = _find_list(
        document,
        "requirement_implementations",
    )
    if requirement_implementations is not None:
        result["requirement_implementations"] = requirement_implementations
    return result


def _normalize_ts_json(content: dict[str, Any]) -> dict[str, Any]:
    document = _find_dict(content, "integrated_test_scenario_json") or content
    result: dict[str, Any] = {}
    fields = {
        "scenarios": ("scenario_json_list", "scenarios"),
        "test_cases": ("test_case_json_list", "test_cases", "cases"),
        "steps": ("step_json_list", "steps"),
        "step_details": ("step_detail_json_list", "step_details"),
    }
    for output_key, aliases in fields.items():
        value = _find_list(document, *aliases)
        if value is not None:
            result[output_key] = value
    result.setdefault("scenarios", [])
    return result


def _find_dict(content: Any, *keys: str) -> dict[str, Any] | None:
    value = _find_value(content, *keys)
    return value if isinstance(value, dict) else None


def _find_list(content: Any, *keys: str) -> list[Any] | None:
    value = _find_value(content, *keys)
    return value if isinstance(value, list) else None


def _find_value(content: Any, *keys: str) -> Any | None:
    if not isinstance(content, dict):
        return None
    for key in keys:
        if key in content and content[key] is not None:
            return content[key]
    for wrapper in ("final_document_json", "result", "content", "data"):
        nested = content.get(wrapper)
        value = _find_value(nested, *keys)
        if value is not None:
            return value
    return None


def _shared_artifact_items(content: Any) -> list[Any]:
    """Document Merge와 동일한 기본 항목 추출 규칙을 재사용합니다."""

    items = artifact_items(content)
    if len(items) == 1 and items[0] is content:
        return []
    return items


def _structure_srs(tables: list[Any], _: list[Any]) -> dict[str, Any]:
    requirements = []
    for table in tables:
        for row in _rows(table):
            if len(row) < 4 or not _looks_like_requirement_id(row[0]):
                continue
            requirements.append(
                {
                    "requirement_id": row[0],
                    "requirement_name": _cell(row, 1),
                    "requirement_type": _cell(row, 2),
                    "description": _cell(row, 3),
                    "source": _split_lines(_cell(row, 4)),
                    "constraints": _split_lines(_cell(row, 5)),
                    "priority": _cell(row, 6),
                    "solution": _cell(row, 7),
                    "validation_criteria": _split_lines(_cell(row, 8)),
                    "note": _cell(row, 9),
                }
            )
    return {"requirements": requirements}


def _structure_interface(tables: list[Any], _: list[Any]) -> dict[str, Any]:
    screens = []
    for table in tables:
        rows = _rows(table)
        joined = " ".join(cell for row in rows for cell in row)
        if "화면ID" in joined and "화면명" in joined and "화면개요" in joined:
            screen = {
                "screen_id": _value_after_label(rows, "화면ID"),
                "screen_name": _value_after_label(rows, "화면명"),
                "screen_type": _value_after_label(rows, "화면유형"),
                "menu_path": _value_after_label(rows, "메뉴경로"),
                "description": _value_after_label(rows, "화면개요"),
                "process_contents": [],
            }
            if screen["screen_id"] or screen["screen_name"]:
                screens.append(screen)
        elif "처리 내용" in joined and screens:
            screens[-1]["process_contents"] = _parse_process_text(
                "\n".join(cell for row in rows for cell in row)
            )
    return {"screens": screens}


def _structure_erd(tables: list[Any], _: list[Any]) -> dict[str, Any]:
    entities = []
    for table in tables:
        rows = _rows(table)
        joined = " ".join(cell for row in rows for cell in row)
        if "엔티티 ID" not in joined or "엔티티명" not in joined:
            continue
        entity_id = _value_after_label(rows, "엔티티 ID")
        entity_name = _value_after_label(rows, "엔티티명")
        header_index = _find_row(rows, "속성명", "타입", "길이")
        columns = []
        if header_index is not None:
            header_map = {
                value.replace(" ", ""): index
                for index, value in enumerate(rows[header_index])
            }
            for index, row in enumerate(rows[header_index + 1 :], start=1):
                logical_name = _mapped_cell_normalized(row, header_map, "속성명")
                data_type = _mapped_cell_normalized(row, header_map, "타입")
                length = _mapped_cell_normalized(row, header_map, "길이")
                if not logical_name and not data_type:
                    continue
                columns.append(
                    {
                        "column_id": _mapped_cell_normalized(row, header_map, "속성ID")
                        or _mapped_cell_normalized(row, header_map, "물리명")
                        or f"{entity_id or 'ENTITY'}-COL-{index:03d}",
                        "logical_name": logical_name,
                        "data_type": f"{data_type}({length})"
                        if data_type and length
                        else data_type,
                        "not_null": _mapped_cell_normalized(row, header_map, "NOTNULL"),
                        "pk": _mapped_cell_normalized(row, header_map, "PK"),
                        "fk": _mapped_cell_normalized(row, header_map, "FK"),
                        "idx": _mapped_cell_normalized(row, header_map, "IDX")
                        or _mapped_cell_normalized(row, header_map, "INX"),
                        "default": _mapped_cell_normalized(row, header_map, "기본값"),
                        "constraint": _mapped_cell_normalized(row, header_map, "제약조건"),
                    }
                )
        entities.append(
            {
                "entity_id": entity_id or entity_name,
                "name": entity_name or entity_id,
                "description": _value_after_label(rows, "엔티티 설명"),
                "columns": columns,
            }
        )
    return {"entities": entities}


def _structure_db(tables: list[Any], _: list[Any]) -> dict[str, Any]:
    parsed_tables = []
    for table in tables:
        rows = _rows(table)
        joined = "\n".join("\t".join(row) for row in rows)
        if "테이블 ID" not in joined or "컬럼 ID" not in joined:
            continue
        header_index = _find_row(rows, "컬럼명", "컬럼 ID", "타입 및 길이")
        if header_index is None:
            continue
        header_map = {value: index for index, value in enumerate(rows[header_index]) if value}
        columns = []
        for row in rows[header_index + 1 :]:
            logical_name = _mapped_cell(row, header_map, "컬럼명")
            column_id = _mapped_cell(row, header_map, "컬럼 ID")
            type_and_length = _mapped_cell(row, header_map, "타입 및 길이")
            if not any((logical_name, column_id, type_and_length)):
                continue
            columns.append(
                {
                    "column_id": column_id or logical_name,
                    "logical_name": logical_name or column_id,
                    "type_and_length": type_and_length,
                    "not_null": _mapped_cell(row, header_map, "Not Null"),
                    "pk": _mapped_cell(row, header_map, "PK"),
                    "fk": _mapped_cell(row, header_map, "FK"),
                    "idx": _mapped_cell(row, header_map, "IDX")
                    or _mapped_cell(row, header_map, "INX"),
                    "default": _mapped_cell(row, header_map, "기본값"),
                    "constraint": _mapped_cell(row, header_map, "제약조건"),
                }
            )
        table_id = _value_after_label(rows, "테이블 ID")
        logical_name = _value_after_label(rows, "테이블명")
        parsed_tables.append(
            {
                "table_id": table_id or logical_name,
                "table_name": logical_name or table_id,
                "database_name": _value_after_label(rows, "데이터베이스 명"),
                "tablespace_name": _value_after_label(rows, "TS명"),
                "trigger_config": _value_after_label(rows, "트리거 구성"),
                "description": _value_after_label(rows, "테이블 설명"),
                "columns": columns,
            }
        )
    return {"tables": parsed_tables}


def _structure_arch(tables: list[Any], paragraphs: list[Any]) -> dict[str, Any]:
    components = []
    for index, table in enumerate(tables, start=1):
        rows = _rows(table)
        joined = " ".join(cell for row in rows for cell in row)
        if "요구사항 내용" not in joined and "구현방안" not in joined:
            continue
        description = _value_after_label(rows, "요구사항 내용")
        implementation = _value_after_label(rows, "구현방안")
        identity_source = description or implementation
        components.append(
            {
                "component_id": _extract_requirement_id(identity_source)
                or f"ARCH-{index:03d}",
                "title": _short_title(identity_source, f"아키텍처 항목 {index}"),
                "description": description,
                "implementation": implementation,
            }
        )
    if not components:
        for index, paragraph in enumerate(paragraphs, start=1):
            text = _text(paragraph)
            if text:
                components.append(
                    {
                        "component_id": _extract_requirement_id(text)
                        or f"ARCH-{index:03d}",
                        "title": _short_title(text, f"아키텍처 항목 {index}"),
                        "description": text,
                    }
                )
    return {"components": components}


def _structure_ts(tables: list[Any], _: list[Any]) -> dict[str, Any]:
    scenarios: dict[str, dict[str, Any]] = {}
    cases: dict[str, dict[str, Any]] = {}
    for table in tables:
        rows = _rows(table)
        joined = " ".join(cell for row in rows for cell in row)
        scenario_id = _value_after_label(rows, "시나리오 ID") or _value_after_label(
            rows, "시나리오ID"
        )
        if scenario_id and ("시나리오명" in joined or "시나리오 명" in joined):
            scenarios.setdefault(
                scenario_id,
                {
                    "scenario_id": scenario_id,
                    "scenario_name": _value_after_label(rows, "시나리오명")
                    or _value_after_label(rows, "시나리오 명"),
                    "description": _value_after_label(rows, "시나리오 설명"),
                    "test_cases": [],
                },
            )
        case_id = _value_after_label(rows, "테스트케이스 ID") or _value_after_label(
            rows, "시험케이스 ID"
        )
        if case_id:
            cases[case_id] = {
                "test_id": case_id,
                "test_case_id": case_id,
                "scenario_id": scenario_id,
                "steps": _parse_ts_steps(rows),
            }
    for case in cases.values():
        if case["scenario_id"] in scenarios:
            scenarios[case["scenario_id"]]["test_cases"].append(case)
    return {"scenarios": list(scenarios.values()) or list(cases.values())}


def _parse_ts_steps(rows: list[list[str]]) -> list[dict[str, Any]]:
    header_index = _find_row(rows, "처리내용", "시험항목", "예상결과")
    if header_index is None:
        return []
    header_map = {
        value.replace(" ", ""): index
        for index, value in enumerate(rows[header_index])
    }
    steps = []
    for index, row in enumerate(rows[header_index + 1 :], start=1):
        content = _mapped_cell_normalized(row, header_map, "처리내용")
        item = _mapped_cell_normalized(row, header_map, "시험항목")
        expected = _mapped_cell_normalized(row, header_map, "예상결과")
        if not any((content, item, expected)):
            continue
        steps.append(
            {
                "step_no": _cell(row, 0) or index,
                "content": content,
                "test_item": item,
                "precondition": _mapped_cell_normalized(row, header_map, "사전조건"),
                "input": _mapped_cell_normalized(row, header_map, "입력값"),
                "expected_result": expected,
                "screen_id": _mapped_cell_normalized(row, header_map, "화면ID"),
            }
        )
    return steps


def _is_document_content(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if any(isinstance(value.get(key), list) for key in ("paragraphs", "pages")):
        return True
    tables = value.get("tables")
    return isinstance(tables, list) and any(isinstance(table, list) for table in tables)


def _root_key(docs_cd: str) -> str:
    return {
        "SRS": "requirements",
        "UI": "screens",
        "ERD": "entities",
        "DB": "tables",
        "ARCH": "components",
        "TS": "scenarios",
    }.get(docs_cd, "items")


def _has_business_items(value: dict[str, Any]) -> bool:
    return any(isinstance(item, list) and item for item in value.values())


def _rows(table: Any) -> list[list[str]]:
    if not isinstance(table, list):
        return []
    return [
        [_text(cell) for cell in row]
        for row in table
        if isinstance(row, list) and any(_text(cell) for cell in row)
    ]


def _text(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("text", "")
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def _cell(row: list[str], index: int) -> str:
    return row[index] if index < len(row) else ""


def _split_lines(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[\n,]+", value) if item.strip()]


def _looks_like_requirement_id(value: str) -> bool:
    return bool(re.match(r"^[A-Z가-힣]{2,10}[-_]\d+", value.strip(), re.IGNORECASE))


def _extract_requirement_id(value: str) -> str:
    match = re.search(r"\b[A-Z]{2,10}[-_]\d+\b", value, re.IGNORECASE)
    return match.group(0) if match else ""


def _value_after_label(rows: list[list[str]], label: str) -> str:
    wanted = label.replace(" ", "")
    for row_index, row in enumerate(rows):
        for column_index, value in enumerate(row):
            if value.replace(" ", "") != wanted:
                continue
            for candidate in row[column_index + 1 :]:
                if candidate and candidate.replace(" ", "") != wanted:
                    return candidate
            if row_index + 1 < len(rows):
                for candidate in rows[row_index + 1]:
                    if candidate and candidate.replace(" ", "") != wanted:
                        return candidate
    return ""


def _find_row(rows: list[list[str]], *labels: str) -> int | None:
    wanted = {label.replace(" ", "") for label in labels}
    for index, row in enumerate(rows):
        if wanted.issubset({cell.replace(" ", "") for cell in row}):
            return index
    return None


def _mapped_cell(row: list[str], header_map: dict[str, int], key: str) -> str:
    index = header_map.get(key)
    return _cell(row, index) if index is not None else ""


def _mapped_cell_normalized(
    row: list[str],
    header_map: dict[str, int],
    key: str,
) -> str:
    index = header_map.get(key.replace(" ", ""))
    return _cell(row, index) if index is not None else ""


def _parse_process_text(value: str) -> list[dict[str, Any]]:
    items = []
    for match in re.finditer(r"-\s*(\d+)\.\s*([^\n·]+)", value):
        items.append(
            {
                "component_id": f"PROCESS-{match.group(1)}",
                "title": match.group(2).strip(),
            }
        )
    return items


def _short_title(value: str, fallback: str) -> str:
    text = _text(value)
    return text[:60].rstrip() if text else fallback
