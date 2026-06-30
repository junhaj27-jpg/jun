"""final_document_json payload를 템플릿 DOCX 양식에 맞춰 생성합니다."""

import copy
import json
import re
import tempfile
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.shared import Inches, Pt
from docx.table import Table

from agents.data_structure_design.processors.table_builder import format_type_and_length
from tools.result import ToolResult, error_result, success_result


def export_docx(
    export_payload: dict[str, Any],
    output_path: str,
    *,
    template_path: str | None = None,
) -> ToolResult:
    """유효한 템플릿이 있으면 산출물별 표 구조를 채우고, 없으면 기본 문서를 생성합니다."""

    try:
        target = Path(output_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        template = Path(template_path).resolve() if template_path else None
        safe_template = _docx_safe_template_path(template) if template else None
        document = (
            Document(str(safe_template))
            if safe_template and safe_template.is_file() and zipfile.is_zipfile(safe_template)
            else Document()
        )

        if safe_template and safe_template.is_file() and zipfile.is_zipfile(safe_template):
            _fill_template_document(document, export_payload)
        else:
            _fill_generic_document(document, export_payload)

        document.save(target)
        return success_result(
            {
                "local_file_path": str(target),
                "file_name": target.name,
                "file_size": target.stat().st_size,
            }
        )
    except Exception as exc:
        return error_result("DOCX_EXPORT_FAILED", str(exc))


def _fill_template_document(document: Any, payload: dict[str, Any]) -> None:
    docs_cd = str(payload.get("docs_cd") or "").upper()
    if docs_cd == "SRS":
        _fill_srs_template(
            document,
            _list_content(payload, "requirement_json_list"),
            _payload_metadata(payload),
        )
    elif docs_cd == "INTERFACE":
        _fill_interface_template(
            document,
            _list_content(payload, "interface_json_list"),
            _list_content(payload, "ui_structure"),
            _payload_metadata(payload),
        )
    elif docs_cd == "TS":
        _fill_ts_template(
            document,
            _dict_content(payload, "integrated_test_scenario_json"),
            _payload_metadata(payload),
        )
    elif docs_cd == "ERD":
        _fill_erd_template(
            document,
            _dict_content(payload, "erd_entity_json"),
            _image_paths(payload),
            _image_groups(payload),
        )
    elif docs_cd == "DB":
        _fill_db_template(document, _dict_content(payload, "db_design_json"))
    elif docs_cd == "ARCH":
        _fill_arch_template(
            document,
            _dict_content(payload, "architecture_document_json"),
            _first_image_path(payload),
        )
    else:
        _fill_generic_document(document, payload)


def _fill_generic_document(document: Any, export_payload: dict[str, Any]) -> None:
    document.add_heading(str(export_payload.get("title", "산출물")), level=0)
    for section_name, section_value in export_payload.get("content", {}).items():
        document.add_heading(section_name, level=1)
        _append_value(document, section_value)

    for image_path in export_payload.get("image_paths", []):
        image = Path(str(image_path))
        if image.is_file():
            document.add_picture(str(_docx_safe_image_path(image)), width=Inches(6.0))


def _fill_srs_template(
    document: Any,
    requirements: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    if len(document.tables) < 2:
        _fill_generic_document(document, {"title": "요구사항 정의서", "content": {"requirement_json_list": requirements}})
        return

    header = document.tables[0]
    _set_cell_safe(header, 1, 1, _pick(metadata, "system_name", "project_name"))
    _set_cell_safe(header, 2, 1, _pick(metadata, "stage_name", default="분석"))
    _set_cell_safe(header, 2, 5, _pick(metadata, "created_date", "write_date", default=str(date.today())))
    _set_cell_safe(header, 2, 7, _pick(metadata, "version"))

    table = document.tables[1]
    base_row_idx = 1
    for index, requirement in enumerate(requirements):
        row = table.rows[base_row_idx + index] if base_row_idx + index < len(table.rows) else table.add_row()
        values = [
            _pick(requirement, "requirement_id"),
            _pick(requirement, "requirement_name"),
            _pick(requirement, "requirement_type"),
            _pick(requirement, "description"),
            _join_source(_pick(requirement, "source")),
            _join(requirement.get("constraints")),
            _join(_pick(requirement, "priority", default=[])),
            _join(_pick(requirement, "solution", "resolution", "mitigation", "handling_plan", default=[])),
            _join(requirement.get("validation_criteria")),
            _clean_srs_note(_pick(requirement, "note")),
        ]
        for cell, value in zip(row.cells, values):
            _set_cell(cell, value)


def _fill_interface_template(
    document: Any,
    screens: list[dict[str, Any]],
    ui_structure: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if len(document.tables) < 5:
        _fill_generic_document(document, {"title": "인터페이스 설계서", "content": {"interface_json_list": screens}})
        return

    _fill_interface_header(document.tables[0], metadata or {})
    _fill_interface_structure_table(document.tables[1], screens, ui_structure or [])
    _fill_repeating_table(
        document.tables[2],
        [[_pick(screen, "screen_id"), _pick(screen, "screen_name", "name")] for screen in screens],
    )

    detail_template = document.tables[3]
    process_template = document.tables[4]
    heading = _find_paragraph(document, "3.1")
    if not screens:
        _fill_interface_detail_table(detail_template, {})
        _fill_interface_process_table(process_template, [])
        return

    for index, screen in enumerate(screens, start=1):
        heading_text = _build_screen_heading(index, screen)
        if index == 1:
            if heading is not None:
                heading.text = ""
                run = heading.add_run(heading_text)
                run.bold = True
                run.font.size = Pt(10)
            detail_table = detail_template
            process_table = process_template
        else:
            anchor = process_template._tbl if index == 2 else process_table._tbl
            page_break = _insert_paragraph_after(document, anchor, page_break=True)
            heading = _insert_paragraph_after(document, page_break._p, heading_text)
            detail_table = _clone_table_after(heading._p, detail_template)
            blank = _insert_paragraph_after(document, detail_table._tbl)
            process_table = _clone_table_after(blank._p, process_template)

        _fill_interface_detail_table(detail_table, screen)
        _fill_interface_process_table(process_table, _process_contents(screen))


def _fill_ts_template(
    document: Any,
    scenario: dict[str, Any],
    metadata: dict[str, Any],
) -> None:
    if len(document.tables) < 3:
        _fill_generic_document(
            document,
            {
                "title": "통합시험 시나리오",
                "content": {"integrated_test_scenario_json": scenario},
            },
        )
        return

    header = document.tables[0]
    _set_cell_safe(header, 1, 1, _pick(metadata, "system_name", "project_name"))
    _set_cell_safe(header, 2, 3, str(date.today()))
    _set_cell_safe(header, 2, 5, _pick(metadata, "version"))

    scenarios = scenario.get("scenario_json_list") or []
    cases = scenario.get("test_case_json_list") or []
    step_details = scenario.get("step_detail_json_list") or []

    cases_by_scenario = _group_by(cases, "scenario_id")
    steps_by_case = _group_by(step_details, "test_case_id")

    scenario_template = document.tables[1]
    case_template = document.tables[2]

    if not scenarios:
        _fill_ts_scenario_table(scenario_template, {}, [], {})
        _fill_ts_case_table(case_template, {}, {}, [])
        return

    anchor = case_template._tbl
    for s_index, scn in enumerate(scenarios):
        scenario_cases = cases_by_scenario.get(scn.get("scenario_id"), [])

        if s_index == 0:
            scn_table = scenario_template
            cs_table = case_template
        else:
            spacer = _insert_paragraph_after(document, anchor)
            scn_table = _clone_table_after(spacer._p, scenario_template)
            anchor = scn_table._tbl

        _fill_ts_scenario_table(scn_table, scn, scenario_cases, steps_by_case)

        for c_index, case in enumerate(scenario_cases):
            case_steps = steps_by_case.get(case.get("test_case_id"), [])
            if s_index == 0 and c_index == 0:
                cs_table = case_template
            else:
                spacer = _insert_paragraph_after(document, anchor)
                cs_table = _clone_table_after(spacer._p, case_template)
            anchor = cs_table._tbl
            _fill_ts_case_table(cs_table, scn, case, case_steps)

        if not scenario_cases:
            # 케이스가 없는 시나리오는 빈 케이스 테이블 1개로 자리만 유지
            spacer = _insert_paragraph_after(document, anchor)
            cs_table = _clone_table_after(spacer._p, case_template)
            anchor = cs_table._tbl
            _fill_ts_case_table(cs_table, scn, {}, [])


def _fill_ts_scenario_table(
    table: Table,
    scenario: dict[str, Any],
    cases: list[dict[str, Any]],
    steps_by_case: dict[str, list[dict[str, Any]]],
) -> None:
    _set_cell_safe(table, 0, 2, _pick(scenario, "scenario_id"))
    _set_cell_safe(table, 1, 2, _pick(scenario, "scenario_name"))
    _set_cell_safe(table, 2, 2, _pick(scenario, "description", "scenario_description"))

    base_row_idx = 4
    if not cases:
        for cell in table.rows[base_row_idx].cells:
            _set_cell(cell, "")
        return

    for index, case in enumerate(cases):
        row = table.rows[base_row_idx + index] if base_row_idx + index < len(table.rows) else table.add_row()
        case_steps = steps_by_case.get(case.get("test_case_id"), [])
        # "시험 절차"는 최종 확정된 step_detail 기준(없으면 test_procedure 초안으로 대체)
        procedure_source = case_steps if case_steps else case.get("test_procedure")
        values = [
            _pick(case, "test_case_id"),
            _pick(case, "test_case_name"),
            _procedure_summary(procedure_source),
            # "시나리오 설명"은 시험 절차의 명사형 요약 (scenario.description과는 별개 필드)
            _pick(case, "scenario_description_summary", default=_procedure_summary(procedure_source)),
            _pick(case, "note"),
        ]
        for cell, value in zip(row.cells, values):
            _set_cell(cell, value)


def _fill_ts_case_table(
    table: Table,
    scenario: dict[str, Any],
    case: dict[str, Any],
    steps: list[dict[str, Any]],
) -> None:
    _set_cell_safe(table, 0, 2, "")  # 차수: 사용자 직접 입력 영역
    _set_cell_safe(table, 1, 2, _pick(scenario, "scenario_id"))
    _set_cell_safe(table, 2, 2, _pick(scenario, "scenario_name"))
    _set_cell_safe(table, 3, 2, _pick(case, "test_case_id"))

    base_row_idx = 6
    if not steps:
        for cell in table.rows[base_row_idx].cells:
            _set_cell(cell, "")
        return

    for index, step in enumerate(steps):
        row = table.rows[base_row_idx + index] if base_row_idx + index < len(table.rows) else table.add_row()
        values = [
            _pick(step, "step_no", default=index + 1),
            _pick(step, "처리내용"),
            _pick(step, "시험항목"),
            _pick(step, "사전조건"),
            _pick(step, "입력값"),
            _pick(step, "예상결과"),
            _pick(step, "화면ID", "screen_id"),
            _pick(step, "test_result", default=""),
            _pick(step, "note"),
        ]
        for cell, value in zip(row.cells, values):
            _set_cell(cell, value)


def _fill_erd_template(
    document: Any,
    erd: dict[str, Any],
    image_paths: list[str],
    image_groups: list[dict[str, Any]],
) -> None:
    entities = _erd_entities(erd)
    relationships = _erd_relationships(erd)
    if len(document.tables) < 3:
        _fill_generic_document(document, {"title": "ERD 설계서", "content": {"erd_entity_json": erd}, "image_paths": image_paths})
        return

    header = document.tables[0]
    _set_cell_safe(header, 1, 1, erd.get("system_name", ""))
    _set_cell_safe(header, 2, 1, erd.get("stage_name", "설계"))
    _set_cell_safe(header, 2, 4, erd.get("created_date", str(date.today())))
    _set_cell_safe(header, 2, 6, erd.get("version", ""))

    erd_table = document.tables[1]
    template_table = document.tables[2]
    _remove_table(erd_table)
    _insert_erd_images_before_anchor(document, _erd_image_anchor(document, template_table), image_paths, image_groups)

    if not entities:
        _fill_erd_entity_table(template_table, {})
        return
    entity_tables = [template_table]
    anchor = template_table._tbl
    for _ in entities[1:]:
        spacer = _insert_paragraph_after(document, anchor)
        spacer.paragraph_format.space_after = Pt(8)
        cloned_table = _clone_table_after(spacer._p, template_table)
        entity_tables.append(cloned_table)
        anchor = cloned_table._tbl
    for table, entity in zip(entity_tables, entities):
        _fill_erd_entity_table(table, entity)


def _fill_db_template(document: Any, design: dict[str, Any]) -> None:
    tables = _db_tables(design)
    if len(document.tables) < 4:
        _fill_generic_document(document, {"title": "DB 설계서", "content": {"db_design_json": design}})
        return

    header = document.tables[0]
    _set_cell_safe(header, 1, 1, design.get("system_name", ""))
    _set_cell_safe(header, 1, 4, design.get("subsystem_name", ""))
    _set_cell_safe(header, 2, 1, design.get("stage_name", "설계"))
    _set_cell_safe(header, 2, 4, design.get("created_date", str(date.today())))
    _set_cell_safe(header, 2, 6, design.get("version", ""))

    _fill_repeating_table(
        document.tables[1],
        [
            [
                design.get("database_id", "DB-001"),
                design.get("database_name", "업무 DB"),
                design.get("owner_department", ""),
                design.get("note", ""),
                "",
            ]
        ],
        base_row_idx=2,
    )

    definition = document.tables[2]
    _set_cell_safe(definition, 0, 1, design.get("database_id", "DB-001"))
    _set_cell_safe(definition, 0, 5, design.get("database_name", "업무 DB"))
    _set_cell_safe(definition, 1, 1, design.get("storage_group", ""))
    _set_cell_safe(definition, 1, 5, design.get("bufferpool", ""))
    _set_cell_safe(definition, 2, 1, design.get("index_bufferpool", ""))
    _fill_repeating_table(
        definition,
        [
            [
                _pick(table, "tablespace_name", default=""),
                _pick(table, "capacity", default="산정 필요"),
                _pick(table, "table_id", "table_name"),
                _pick(table, "table_name", "physical_name"),
                f"IX_{_pick(table, 'table_name', 'physical_name')}",
                "산정 필요",
                _pick(table, "note"),
            ]
            for table in tables
        ],
        base_row_idx=3,
    )

    template_table = document.tables[3]
    if not tables:
        _fill_db_table_spec(template_table, {})
        return
    _clone_repeating_tables_with_spacing(document, template_table, len(tables) - 1)
    for table, item in zip(document.tables[3 : 3 + len(tables)], tables):
        _fill_db_table_spec(table, item)


def _fill_arch_template(document: Any, arch_doc: dict[str, Any], image_path: str | None) -> None:
    if len(document.tables) < 3:
        _fill_generic_document(document, {"title": "아키텍처 설계서", "content": {"architecture_document_json": arch_doc}, "image_paths": [image_path] if image_path else []})
        return

    header = document.tables[0]
    _set_cell_safe(header, 1, 1, _pick(arch_doc, "system_name", "project_name"))
    _set_cell_safe(header, 1, 4, _pick(arch_doc, "subsystem_name"))
    _set_cell_safe(header, 2, 1, _pick(arch_doc, "stage_name", default="설계"))
    _set_cell_safe(header, 2, 4, _pick(arch_doc, "created_date", default=str(date.today())))
    _set_cell_safe(header, 2, 6, _pick(arch_doc, "version"))

    _insert_image_in_cell_safe(document.tables[1].cell(0, 0), image_path, width=6.2)

    requirements = _arch_requirement_items(arch_doc)
    template_table = document.tables[2]
    if not requirements:
        _fill_arch_requirement_table(template_table, {}, arch_doc)
        return
    anchor = template_table._tbl
    for _ in requirements[1:]:
        spacer = _insert_paragraph_after(document, anchor)
        spacer.paragraph_format.space_after = Pt(8)
        cloned_table = _clone_table_after(spacer._p, template_table)
        anchor = cloned_table._tbl
    for table, requirement in zip(document.tables[2 : 2 + len(requirements)], requirements):
        _fill_arch_requirement_table(table, requirement, arch_doc)


def _fill_interface_header(table: Table, metadata: dict[str, Any]) -> None:
    _set_cell_safe(table, 1, 1, _pick(metadata, "system_name", "project_name"))
    _set_cell_safe(table, 2, 3, str(date.today()))
    _set_cell_safe(table, 2, 5, _pick(metadata, "version"))


def _fill_interface_structure_table(
    table: Table,
    screens: list[dict[str, Any]],
    ui_structure: list[dict[str, Any]] | None = None,
) -> None:
    rows = []
    for item in ui_structure or []:
        rows.append(
            [
                _pick(item, "level1"),
                _pick(item, "level2"),
                _pick(item, "level3"),
                _pick(item, "level4"),
            ]
        )
    if rows:
        _fill_repeating_table(table, rows)
        return
    for screen in screens:
        menu_path = str(_pick(screen, "menu_path", default=""))
        levels = [part.strip() for part in menu_path.split(">") if part.strip()]
        rows.append(
            [
                levels[0] if len(levels) > 0 else _pick(screen, "screen_name", "name"),
                levels[1] if len(levels) > 1 else "",
                levels[2] if len(levels) > 2 else "",
                levels[3] if len(levels) > 3 else "",
            ]
        )
    _fill_repeating_table(table, rows)


def _fill_interface_detail_table(table: Table, screen: dict[str, Any]) -> None:
    _set_cell_safe(table, 0, 0, "화면ID")
    _set_cell_safe(table, 0, 1, _pick(screen, "screen_id"))
    _set_cell_safe(table, 0, 2, "화면명")
    _set_cell_safe(table, 0, 3, _pick(screen, "screen_name", "name"))
    _set_cell_safe(table, 1, 0, "화면유형")
    _set_cell_safe(table, 1, 1, _pick(screen, "screen_type", default=""))
    _set_cell_safe(table, 1, 2, "메뉴경로")
    _set_cell_safe(table, 1, 3, _pick(screen, "menu_path", default=""))
    _set_cell_safe(table, 2, 0, "화면개요")
    _set_cell_safe(table, 2, 1, _pick(screen, "screen_overview", "description"))
    image_path = _pick(screen, "annotated_image_path", "image_path")
    if image_path:
        _insert_image_in_cell_safe(table.cell(3, 0), str(image_path), width=6.7)


def _fill_interface_process_table(table: Table, items: list[dict[str, Any]]) -> None:
    _set_cell_safe(table, 0, 0, "처리 내용")
    body = table.cell(1, 0)
    body.text = ""
    if not items:
        body.paragraphs[0].add_run("- 처리 내용 없음")
        return
    first = True
    for index, item in enumerate(items, start=1):
        paragraph = body.paragraphs[0] if first else body.add_paragraph()
        first = False
        no = _pick(item, "no", default=index)
        title = _pick(item, "title", "name", default=f"처리 {no}")
        paragraph.add_run(f"- {no}. {title}").bold = True
        description = _pick(item, "description", "content")
        basis = _pick(item, "requirement_basis", "basis")
        if description:
            body.add_paragraph(f"  · [{no}] {description}")
        if basis:
            body.add_paragraph(f"  · 근거: {basis}")


def _fill_erd_entity_table(table: Table, entity: dict[str, Any]) -> None:
    _set_cell_safe(table, 0, 2, _pick(entity, "entity_id", "table_id", default=""))
    _set_cell_safe(table, 0, 7, _pick(entity, "entity_name", "logical_name", "table_logical_name"))
    _set_cell_safe(table, 1, 4, _pick(entity, "entity_description", "table_description", "table_comment", "description"))
    rows = [_erd_column_to_row(column) for column in _entity_columns(entity)]
    _fill_repeating_table(table, rows, base_row_idx=3)


def _fill_db_table_spec(table: Table, item: dict[str, Any]) -> None:
    table_name = _pick(item, "table_name", "physical_name")
    _set_cell_safe(table, 0, 1, _pick(item, "table_id", default=table_name))
    _set_cell_safe(table, 0, 6, _pick(item, "table_logical_name", "logical_name", default=table_name))
    _set_cell_safe(table, 1, 1, _pick(item, "database_name", default="업무 DB"))
    _set_cell_safe(table, 1, 6, _pick(item, "tablespace_name", default=""))
    _set_cell_safe(table, 2, 1, _pick(item, "trigger_config", default=""))
    _set_cell_safe(table, 3, 1, _pick(item, "table_description", "description", "table_comment"))
    _fill_repeating_table(
        table,
        [
            [
                _pick(item, "initial_count", default="0"),
                _pick(item, "daily_growth", default="산정 필요"),
                _pick(item, "retention_period", default="업무 기준에 따름"),
                _pick(item, "max_count", default="산정 필요"),
                _pick(item, "capacity", default="산정 필요"),
                _pick(item, "note", default=""),
            ]
        ],
        base_row_idx=5,
    )
    _fill_repeating_table(
        table,
        [_db_column_to_row(column) for column in _entity_columns(item)],
        base_row_idx=7,
    )


def _fill_arch_requirement_table(table: Table, requirement: dict[str, Any], arch_doc: dict[str, Any]) -> None:
    content = _pick(requirement, "description", "detail_text", "content")
    implementation = _arch_implementation_text(requirement, arch_doc)
    if _set_arch_labeled_row(table, "요구사항 내용", content):
        _set_arch_labeled_row(table, "구현방안", implementation)
        return
    _set_cell_safe(table, 1, 0, content)
    _set_cell_safe(table, 3, 0, implementation)


def _append_value(document: Any, value: Any) -> None:
    if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
        keys = list(dict.fromkeys(key for item in value for key in item))
        table = document.add_table(rows=1, cols=len(keys))
        for index, key in enumerate(keys):
            table.rows[0].cells[index].text = str(key)
        for item in value:
            cells = table.add_row().cells
            for index, key in enumerate(keys):
                cells[index].text = _to_text(item.get(key))
        return
    document.add_paragraph(_to_text(value))


def _fill_repeating_table(table: Table, rows: list[list[Any]], base_row_idx: int = 1) -> None:
    for row_idx, values in enumerate(rows):
        row = table.rows[base_row_idx + row_idx] if base_row_idx + row_idx < len(table.rows) else table.add_row()
        for cell, value in zip(row.cells, values):
            _set_cell(cell, value)


def _group_by(items: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(item.get(key), []).append(item)
    return grouped


def _procedure_summary(test_procedure: Any) -> str:
    if not isinstance(test_procedure, list):
        return _to_plain_text(test_procedure)
    lines = []
    for index, proc in enumerate(test_procedure, start=1):
        if isinstance(proc, dict):
            text = proc.get("처리내용") or proc.get("process") or proc.get("action") or ""
        else:
            text = str(proc)
        if text:
            lines.append(f"{index}. {text}")
    return "\n".join(lines)


def _set_cell_safe(table: Table, row_idx: int, col_idx: int, value: Any) -> None:
    if row_idx < len(table.rows) and col_idx < len(table.rows[row_idx].cells):
        _set_cell(table.cell(row_idx, col_idx), value)


def _set_cell(cell: Any, value: Any) -> None:
    cell.text = _to_plain_text(value)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    for paragraph in cell.paragraphs:
        paragraph.paragraph_format.space_after = Pt(0)
        for run in paragraph.runs:
            run.font.size = Pt(8)


def _insert_image_in_cell_safe(
    cell: Any,
    image_path: str | None,
    *,
    width: float,
    trailing_text: str = "",
) -> None:
    image = Path(str(image_path)) if image_path else None
    if not image or not image.is_file():
        return
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.add_run().add_picture(str(_docx_safe_image_path(image)), width=Inches(width))
    if trailing_text.strip():
        cell.add_paragraph(trailing_text)


def _insert_erd_images_before_anchor(
    document: Any,
    anchor: Any,
    image_paths: list[str],
    image_groups: list[dict[str, Any]],
) -> None:
    for index, image_path in reversed(list(enumerate(image_paths, start=1))):
        image = Path(str(image_path)) if image_path else None
        if not image or not image.is_file():
            continue
        group = image_groups[index - 1] if index - 1 < len(image_groups) else {}
        image_width = _image_insert_width(document, image, str(group.get("group_type") or ""))
        image_paragraph = _insert_paragraph_before(document, anchor)
        image_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        image_paragraph.paragraph_format.keep_together = True
        image_paragraph.paragraph_format.space_after = Pt(6)
        image_paragraph.add_run().add_picture(str(_docx_safe_image_path(image)), width=Inches(image_width))
        title_paragraph = _insert_paragraph_before(document, image_paragraph._p, _erd_diagram_caption(group, index))
        title_paragraph.paragraph_format.keep_with_next = True
        title_paragraph.paragraph_format.keep_together = True
        title_paragraph.paragraph_format.space_before = Pt(8)
        title_paragraph.paragraph_format.space_after = Pt(4)
        anchor = title_paragraph._p


def _erd_image_anchor(document: Any, fallback_table: Table) -> Any:
    for paragraph in document.paragraphs:
        if "엔티티명세서" in paragraph.text.replace(" ", ""):
            return paragraph._p
    return fallback_table._tbl


def _image_insert_width(document: Any, image_path: Path, group_type: str = "") -> float:
    width_ratio = 0.7 if group_type == "orphan" else 0.95
    max_width = _usable_width_inches(document) * width_ratio
    max_height = _usable_height_inches(document) * 0.8
    try:
        from PIL import Image

        with Image.open(image_path) as image:
            image.load()
            width_px, height_px = image.size
        if width_px <= 0 or height_px <= 0:
            return max_width
        rendered_height = max_width * height_px / width_px
        if rendered_height <= max_height:
            return max_width
        return max(1.0, max_height * width_px / height_px)
    except Exception:
        return max_width


def _usable_width_inches(document: Any) -> float:
    try:
        section = document.sections[0]
        usable = section.page_width - section.left_margin - section.right_margin
        return max(1.0, usable / 914400)
    except Exception:
        return 9.5


def _usable_height_inches(document: Any) -> float:
    try:
        section = document.sections[0]
        usable = section.page_height - section.top_margin - section.bottom_margin
        return max(1.0, usable / 914400)
    except Exception:
        return 6.5


def _docx_safe_image_path(image_path: Path) -> Path:
    """python-docx가 파싱하지 못하는 PNG 메타데이터를 제거한 삽입용 이미지를 반환합니다."""

    try:
        from PIL import Image

        with Image.open(image_path) as image:
            image.load()
            mode = "RGBA" if image.mode in {"RGBA", "LA", "P"} else "RGB"
            safe_image = image.convert(mode)
            safe_dir = Path(tempfile.gettempdir()) / "alpled_docx_images"
            safe_dir.mkdir(parents=True, exist_ok=True)
            safe_path = safe_dir / f"{image_path.stem}_docx_safe.png"
            safe_image.save(safe_path, format="PNG", optimize=True)
            return safe_path
    except Exception:
        return image_path


def _docx_safe_template_path(template_path: Path) -> Path:
    """python-docx가 읽지 못하는 소수 twips 값을 정수로 바꾼 임시 템플릿을 반환합니다."""

    if not template_path.is_file() or not zipfile.is_zipfile(template_path):
        return template_path
    safe_dir = Path(tempfile.gettempdir()) / "alpled_docx_templates"
    safe_dir.mkdir(parents=True, exist_ok=True)
    safe_path = safe_dir / f"{template_path.stem}_docx_safe.docx"
    with zipfile.ZipFile(template_path, "r") as source, zipfile.ZipFile(safe_path, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename.endswith(".xml"):
                text = data.decode("utf-8", errors="ignore")
                text = re.sub(
                    r'(w:w=")([0-9]+\.[0-9]+)(")',
                    lambda match: f'{match.group(1)}{int(round(float(match.group(2))))}{match.group(3)}',
                    text,
                )
                data = text.encode("utf-8")
            target.writestr(item, data)
    return safe_path


def _clone_table_after(block: Any, table: Table) -> Table:
    new_tbl = copy.deepcopy(table._tbl)
    block.addnext(new_tbl)
    return Table(new_tbl, table._parent)


def _remove_table(table: Table) -> None:
    element = table._tbl
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)


def _clone_repeating_tables_with_spacing(document: Any, template_table: Table, clone_count: int) -> None:
    anchor = template_table._tbl
    for _ in range(max(0, clone_count)):
        spacer = _insert_paragraph_after(document, anchor)
        spacer.paragraph_format.space_after = Pt(8)
        cloned_table = _clone_table_after(spacer._p, template_table)
        anchor = cloned_table._tbl


def _insert_paragraph_after(document: Any, block: Any, text: str = "", page_break: bool = False) -> Any:
    paragraph = document.add_paragraph()
    paragraph._p.getparent().remove(paragraph._p)
    block.addnext(paragraph._p)
    if page_break:
        paragraph.add_run().add_break(WD_BREAK.PAGE)
    if text:
        run = paragraph.add_run(text)
        run.bold = True
        run.font.size = Pt(10)
    return paragraph


def _insert_paragraph_before(document: Any, block: Any, text: str = "") -> Any:
    paragraph = document.add_paragraph()
    paragraph._p.getparent().remove(paragraph._p)
    block.addprevious(paragraph._p)
    if text:
        run = paragraph.add_run(text)
        run.bold = True
        run.font.size = Pt(10)
    return paragraph


def _find_paragraph(document: Any, prefix: str) -> Any | None:
    for paragraph in document.paragraphs:
        if paragraph.text.strip().startswith(prefix):
            return paragraph
    return None


def _list_content(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get("content", {}).get(key)
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _dict_content(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get("content", {}).get(key)
    return value if isinstance(value, dict) else {}


def _payload_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("metadata")
    return value if isinstance(value, dict) else {}


def _first_image_path(payload: dict[str, Any]) -> str | None:
    images = payload.get("image_paths") or []
    return str(images[0]) if images else None


def _image_paths(payload: dict[str, Any]) -> list[str]:
    images = payload.get("image_paths") or []
    return [str(image) for image in images if image]


def _image_groups(payload: dict[str, Any]) -> list[dict[str, Any]]:
    groups = payload.get("image_groups") or []
    return [group for group in groups if isinstance(group, dict)] if isinstance(groups, list) else []


def _erd_diagram_caption(
    group: dict[str, Any],
    index: int,
) -> str:
    group_type = str(group.get("group_type") or "")
    if group_type == "orphan":
        suffix = int(group.get("orphan_index") or _group_numeric_suffix(group, index))
        return f"1.{index} 단독 엔티티 ERD - {suffix}"
    group_name = str(group.get("group_name") or "").strip()
    if group_name:
        return f"1.{index} 관계 그룹 ERD - {group_name}"
    return f"1.{index} 관계 그룹 ERD"


def _group_numeric_suffix(group: dict[str, Any], fallback: int) -> int:
    group_id = str(group.get("group_id") or "")
    suffix = group_id.rsplit("-", 1)[-1]
    return int(suffix) if suffix.isdigit() else fallback


def _pick(data: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return default


def _join(value: Any) -> str:
    if isinstance(value, list):
        return _xml_safe_text("\n".join(_to_plain_text(item) for item in value))
    return _to_plain_text(value)


def _join_source(value: Any) -> str:
    if isinstance(value, list):
        items = [_to_plain_text(item) for item in value]
    else:
        text = _to_plain_text(value)
        items = re.findall(r"[A-Z]{2,5}-\d{2,4}", text) or [text]
    return _xml_safe_text(",\n".join(item for item in items if item))


def _clean_srs_note(value: Any) -> str:
    text = _to_plain_text(value)
    text = re.sub(r"\s*(반영|참고)\s*근거\s*:\s*(?:[A-Z]{2,5}-\d{2,4}\s*,?\s*)+\.?", "", text)
    return _xml_safe_text(text.strip(" /;"))


def _to_plain_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return _xml_safe_text("\n".join(_to_plain_text(item) for item in value))
    if isinstance(value, dict):
        return _xml_safe_text(json.dumps(value, ensure_ascii=False))
    return _xml_safe_text(str(value).strip())


def _to_text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return _xml_safe_text(json.dumps(value, ensure_ascii=False, indent=2))
    return "" if value is None else _xml_safe_text(str(value))


def _xml_safe_text(value: str) -> str:
    """Remove characters that cannot be written into WordprocessingML XML."""
    return re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\uD800-\uDFFF\uFFFE\uFFFF]", "", value)


def _process_contents(screen: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("process_contents", "actions", "user_actions"):
        value = screen.get(key)
        if isinstance(value, list):
            return [item if isinstance(item, dict) else {"description": item} for item in value]
    description = _pick(screen, "description")
    return [{"title": "화면 설명", "description": description}] if description else []


def _build_screen_heading(index: int, screen: dict[str, Any]) -> str:
    screen_id = str(_pick(screen, "screen_id", default=f"UI-{index:03d}"))
    suffix = screen_id.split("-")[-1]
    no = int(suffix) if suffix.isdigit() else index
    return f"3.{no} {_pick(screen, 'screen_name', 'name')}".strip()


def _erd_entities(erd: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(erd.get("entities"), list):
        return [item for item in erd["entities"] if isinstance(item, dict)]
    entities = []
    for index, table in enumerate(_db_tables(erd), start=1):
        entities.append(
            {
                "entity_id": _pick(table, "entity_id", "table_id", default=f"ENT-{index:03d}"),
                "entity_name": _pick(table, "entity_name", "logical_name", "table_logical_name"),
                "entity_description": _short_text(_pick(table, "entity_description", "description", "table_comment"), 80),
                "columns": _entity_columns(table),
            }
        )
    return entities


def _erd_relationships(erd: dict[str, Any]) -> list[dict[str, Any]]:
    value = erd.get("relationships") or erd.get("relationship_list") or []
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _relationship_text(item: dict[str, Any]) -> str:
    return (
        f"{_pick(item, 'from_entity', 'from_table')} "
        f"{_pick(item, 'relationship', 'type', default='1:N')} "
        f"{_pick(item, 'to_entity', 'to_table')} - "
        f"{_pick(item, 'description', 'from_column')}"
    ).strip(" -")


def _entity_columns(item: dict[str, Any]) -> list[dict[str, Any]]:
    value = item.get("columns") or item.get("column_list") or []
    return [column for column in value if isinstance(column, dict)] if isinstance(value, list) else []


def _erd_column_to_row(column: dict[str, Any]) -> list[Any]:
    constraints = column.get("constraints")
    data_type, length = _split_data_type(_pick(column, "type", "data_type"))
    physical_name = _pick(column, "physical_name", "column_name", "name")
    return [
        _pick(column, "attribute_name", "logical_name", "column_logical_name"),
        _short_text(_clean_optional_text(_pick(column, "synonym", default="")), 30),
        data_type,
        _pick(column, "length", default=length),
        _yes_no(not bool(column.get("nullable", True))) or _pick(column, "not_null"),
        _erd_key_marker(column, constraints, "PK"),
        _erd_key_marker(column, constraints, "FK"),
        _yes_no(
            _pick(column, "idx", "inx")
            or column.get("is_pk")
            or column.get("is_fk")
            or _contains_constraint(constraints, "PK", "FK", "INDEX", "IDX")
        ),
        _pick(column, "default", default=""),
        _short_text(_column_constraint_text(column), 60),
    ]


def _split_data_type(value: Any) -> tuple[str, str]:
    text = _to_plain_text(value).strip()
    match = re.match(r"^([A-Za-z가-힣_]+)\s*\(([^)]+)\)$", text)
    if match:
        return match.group(1).upper(), match.group(2).strip()
    return text.upper(), ""


def _short_text(value: Any, max_length: int) -> str:
    text = _to_plain_text(value).replace("\n", " ").strip()
    return text if len(text) <= max_length else text[:max_length].rstrip()


def _db_tables(design: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("tables", "entities", "table_specification_json"):
        value = design.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _db_column_to_row(column: dict[str, Any]) -> list[Any]:
    constraints = column.get("constraints")
    return [
        _pick(column, "column_logical_name", "logical_name", "description", "column_name", "name"),
        _pick(column, "column_id", "physical_name", "column_name", "name"),
        format_type_and_length(
            _pick(column, "type_and_length", "data_type", "type"),
            _pick(column, "length"),
        ),
        _yes_no(not bool(column.get("nullable", True))) or _pick(column, "not_null"),
        _yes_no(_pick(column, "pk") or column.get("is_pk") or _contains_constraint(constraints, "PK")),
        _yes_no(_pick(column, "fk") or column.get("is_fk") or _contains_constraint(constraints, "FK")),
        _yes_no(_pick(column, "idx", "inx") or column.get("is_pk") or column.get("is_fk") or _contains_constraint(constraints, "PK", "FK", "INDEX", "IDX")),
        _pick(column, "default", default=""),
        _column_constraint_text(column),
    ]


def _yes_no(value: Any) -> str:
    if isinstance(value, str):
        return "Y" if value.upper() in {"Y", "YES", "TRUE", "PK", "FK"} else ""
    return "Y" if bool(value) else ""


def _contains_constraint(value: Any, *needles: str) -> str:
    if not needles:
        return ""
    if isinstance(value, list):
        return "Y" if any(any(needle.upper() in str(item).upper() for needle in needles) for item in value) else ""
    return "Y" if any(needle.upper() in str(value).upper() for needle in needles) else ""


def _erd_key_marker(column: dict[str, Any], constraints: Any, marker: str) -> str:
    explicit = _pick(column, marker.lower())
    if explicit:
        return _yes_no(explicit)
    if marker == "PK" and column.get("is_pk"):
        return "Y"
    if marker == "FK" and column.get("is_fk"):
        return "Y"
    return _contains_constraint(constraints, marker)


def _column_constraint_text(column: dict[str, Any]) -> str:
    explicit = _pick(column, "constraint")
    if explicit and not _looks_like_standard_evidence(explicit):
        return explicit
    constraints = column.get("constraints")
    if isinstance(constraints, list):
        filtered = [
            str(item)
            for item in constraints
            if str(item).upper() not in {"PK", "FK", "INDEX", "IDX", "NOT NULL"}
            and not _looks_like_standard_evidence(str(item))
        ]
        if filtered:
            return ", ".join(filtered)
    return ""


def _looks_like_standard_evidence(text: Any) -> bool:
    normalized = re.sub(r"\s+", " ", _to_plain_text(text).strip().lstrip("\ufeff"))
    if not normalized:
        return False
    if re.search(
        r"(?:^|[\s\[\(])(?:공통표준(?:용어|단어|도메인)|standard[_ -]?(?:term|word|domain))[_\-\s]*\d*\s*[:：]",
        normalized,
        re.IGNORECASE,
    ):
        return True
    if re.search(r"\d+\s*자리\s*이내\s*문자(?:로)?\s*저장", normalized):
        return True
    if re.search(r"(?:문자열?|숫자|날짜|일시)(?:로)?\s*저장", normalized):
        return True
    if re.search(r"(?:Y/N|YN|코드|문자열?|숫자|날짜|일시|BOOLEAN|BOOL).{0,24}(?:형식|포맷|타입|도메인).{0,24}저장", normalized, re.IGNORECASE):
        return True
    if re.search(r"(?:형식|포맷|타입|도메인)(?:으로)?\s*저장", normalized):
        return True
    return False


def _clean_optional_text(value: Any) -> str:
    text = _to_plain_text(value)
    if text in {"", "-", "–", "—", "N/A", "n/a", "없음", "해당 없음", "null", "None"}:
        return ""
    return text


def _arch_requirement_items(arch_doc: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("requirements", "requirement_implementations", "drivers", "components"):
        value = arch_doc.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    overview = _pick(arch_doc, "overview")
    return [{"description": overview}] if overview else []


def _set_arch_labeled_row(table: Table, label: str, value: Any) -> bool:
    for row_idx, row in enumerate(table.rows):
        first_cell_text = row.cells[0].text.replace(" ", "")
        if label.replace(" ", "") in first_cell_text:
            target_row = row_idx + 1
            if target_row < len(table.rows):
                _set_cell_safe(table, target_row, 0, value)
                return True
    return False


def _arch_implementation_text(requirement: dict[str, Any], arch_doc: dict[str, Any]) -> str:
    explicit = _pick(requirement, "implementation", "implementation_strategy")
    if explicit:
        return explicit

    component_text = _arch_component_implementation_text(requirement, arch_doc)
    if component_text:
        return component_text

    driver_text = _arch_driver_implementation_text(requirement, arch_doc)
    if driver_text:
        return driver_text

    direct = _pick(requirement, "description", "detail_text", "content")
    components = arch_doc.get("components") or arch_doc.get("component_descriptions") or []
    relations = arch_doc.get("relations") or arch_doc.get("edges") or []
    parts = [direct] if direct else []
    if isinstance(components, list) and components:
        component_names = [
            _pick(item, "name", "component_name", "id")
            for item in components
            if isinstance(item, dict)
        ]
        parts.append("구성요소는 " + ", ".join(component_names[:6]) + " 중심으로 구성합니다.")
    if isinstance(relations, list) and relations:
        relation_summary = [_arch_relation_text(item) for item in relations if isinstance(item, dict)]
        parts.append("주요 연계는 " + "; ".join(relation_summary[:4]) + " 방식으로 설계합니다.")
    return "\n".join(part for part in parts if part)


def _arch_component_implementation_text(requirement: dict[str, Any], arch_doc: dict[str, Any]) -> str:
    component_id = _pick(requirement, "component_id", "id")
    component_name = _pick(requirement, "name", "component_name")
    if not component_id and not component_name:
        return ""

    layer = _pick(requirement, "layer", default="Application Layer")
    description = _pick(requirement, "description", "role")
    relations = _arch_related_relations(component_id, component_name, arch_doc)
    deployment = arch_doc.get("deployment_environment") if isinstance(arch_doc.get("deployment_environment"), dict) else {}

    sentences = [
        f"{component_name or component_id}는 {layer}에 배치하여 {description or '담당 기능을 독립적으로 처리'}하도록 설계합니다.",
    ]
    if relations:
        sentences.append(
            "주요 연계는 "
            + "; ".join(_arch_relation_text(item) for item in relations[:4])
            + " 흐름으로 정의합니다."
        )
    if deployment:
        env_bits = [
            _pick(deployment, "environment"),
            _pick(deployment, "web_was"),
            _pick(deployment, "dbms"),
            _pick(deployment, "storage"),
            _pick(deployment, "vector_db"),
            _pick(deployment, "llm_server"),
        ]
        env_text = ", ".join(bit for bit in env_bits if bit)
        if env_text:
            sentences.append(f"배포 및 운영 기준은 {env_text} 구성을 적용합니다.")
    return " ".join(sentences)


def _arch_driver_implementation_text(requirement: dict[str, Any], arch_doc: dict[str, Any]) -> str:
    driver_id = _pick(requirement, "driver_id")
    category = _pick(requirement, "category")
    name = _pick(requirement, "name")
    description = _pick(requirement, "description")
    if not driver_id and not category:
        return ""

    components = arch_doc.get("components") or []
    component_names = [
        _pick(item, "name", "component_name", "component_id")
        for item in components
        if isinstance(item, dict)
        and (
            not category
            or category in item.get("driver_categories", [])
            or category.lower() in str(item).lower()
        )
    ]
    target_text = ", ".join(component_names[:5]) if component_names else "관련 구성요소"
    return (
        f"{name or category}는 {target_text}에 반영합니다. "
        f"{description or '품질 속성 요구사항을 설계 기준으로 적용합니다.'}"
    )


def _arch_related_relations(
    component_id: str,
    component_name: str,
    arch_doc: dict[str, Any],
) -> list[dict[str, Any]]:
    relations = arch_doc.get("relations") or arch_doc.get("edges") or []
    if not isinstance(relations, list):
        return []
    keys = {value for value in (component_id, component_name) if value}
    return [
        item
        for item in relations
        if isinstance(item, dict)
        and (
            _pick(item, "source", "from", "from_component") in keys
            or _pick(item, "target", "to", "to_component") in keys
        )
    ]


def _arch_relation_text(item: dict[str, Any]) -> str:
    source = _pick(item, "source", "from", "from_component", "from_entity", "from_table")
    target = _pick(item, "target", "to", "to_component", "to_entity", "to_table")
    description = _pick(item, "description", "label", "type")
    if source and target and description:
        return f"{source} -> {target}: {description}"
    if source and target:
        return f"{source} -> {target}: 연계"
    return _relationship_text(item)
