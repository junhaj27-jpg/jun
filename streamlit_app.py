import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import streamlit as st


ROOT_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = ROOT_DIR / "json_temp" / "streamlit_uploads"
OUTPUT_DIR = ROOT_DIR / "output"
JSON_TEMP_DIR = ROOT_DIR / "json_temp"


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _save_uploaded_file(uploaded_file, prefix: str) -> str | None:
    if uploaded_file is None:
        return None

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = Path(uploaded_file.name).name
    path = UPLOAD_DIR / f"{prefix}_{_timestamp()}_{safe_name}"
    path.write_bytes(uploaded_file.getbuffer())
    return str(path)


def _save_uploaded_files(uploaded_files, prefix: str) -> list[str]:
    return [
        saved_path
        for uploaded_file in uploaded_files or []
        if (saved_path := _save_uploaded_file(uploaded_file, prefix))
    ]


def _download_file(path: str | None, label: str) -> None:
    if not path:
        return

    file_path = Path(path)
    if not file_path.exists():
        st.caption(f"{label}: 파일을 찾지 못했습니다. {file_path}")
        return

    st.download_button(
        label=f"{label} 다운로드",
        data=file_path.read_bytes(),
        file_name=file_path.name,
        mime="application/octet-stream",
    )


def _show_result_paths(result: dict[str, Any], keys: list[tuple[str, str]]) -> None:
    for key, label in keys:
        value = result.get(key)
        if value:
            st.write(f"{label}: `{value}`")
            _download_file(value, label)


def _load_json_preview(path: str | None) -> None:
    if not path or not Path(path).exists():
        return
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return
    with st.expander("JSON 미리보기", expanded=False):
        st.json(data)


def render_erd_tab() -> None:
    st.subheader("ERD 설계서 생성")
    requirement_upload = st.file_uploader("요구사항 JSON 업로드", type=["json"], key="erd_req_upload")
    requirement_path = st.text_input(
        "요구사항 JSON 경로",
        value="./data/requirements/requirement.json",
        key="erd_req_path",
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        use_llm = st.checkbox("LLM 사용", value=True, key="erd_use_llm")
    with col2:
        use_mermaid = st.checkbox("Mermaid 포함", value=True, key="erd_use_mermaid")
    with col3:
        fast_table = st.checkbox("빠른 표 생성", value=True, key="erd_fast_table")

    output_json_path = st.text_input(
        "출력 JSON 경로",
        value=f"./json_temp/erd_agent_output_{_timestamp()}.json",
        key="erd_output_json",
    )
    output_docx_path = st.text_input(
        "출력 DOCX 경로",
        value=f"./output/erd_design_{_timestamp()}.docx",
        key="erd_output_docx",
    )

    if st.button("ERD 생성 실행", type="primary", key="run_erd"):
        uploaded_path = _save_uploaded_file(requirement_upload, "erd_requirement")
        with st.spinner("ERD 생성 중입니다..."):
            from workflows.erd_workflow import compile_erd_graph

            result = compile_erd_graph().invoke(
                {
                    "requirement_json_path": uploaded_path or requirement_path,
                    "use_llm": use_llm,
                    "use_mermaid": use_mermaid,
                    "fast_table": fast_table,
                    "output_json_path": output_json_path,
                    "output_docx_path": output_docx_path,
                }
            )

        if result.get("status") != "VALID":
            st.error("ERD 생성 실패")
            st.write(result.get("validation_errors", []))
            return
        st.success("ERD 생성 완료")
        _show_result_paths(result, [("output_json_path", "ERD JSON"), ("erd_docx_path", "ERD DOCX")])
        _load_json_preview(result.get("output_json_path"))


def render_db_tab() -> None:
    st.subheader("DB 설계서 생성")
    requirement_upload = st.file_uploader("요구사항 JSON 업로드", type=["json"], key="db_req_upload")
    erd_upload = st.file_uploader("ERD DOCX 업로드", type=["docx"], key="db_erd_upload")

    requirement_path = st.text_input(
        "요구사항 JSON 경로",
        value="./data/requirements/requirement.json",
        key="db_req_path",
    )
    erd_docx_path = st.text_input(
        "ERD DOCX 경로",
        value="./output/엔티티 관계 모형 설계서.docx",
        key="db_erd_path",
    )
    use_rag = st.checkbox("RAG 보강 사용", value=True, key="db_use_rag")
    output_json_path = st.text_input(
        "출력 JSON 경로",
        value=f"./json_temp/db_design_output_{_timestamp()}.json",
        key="db_output_json",
    )
    output_docx_path = st.text_input(
        "출력 DOCX 경로",
        value=f"./output/database_design_{_timestamp()}.docx",
        key="db_output_docx",
    )

    if st.button("DB 설계서 생성 실행", type="primary", key="run_db"):
        uploaded_req_path = _save_uploaded_file(requirement_upload, "db_requirement")
        uploaded_erd_path = _save_uploaded_file(erd_upload, "db_erd")
        with st.spinner("DB 설계서 생성 중입니다..."):
            from workflows.db_design_workflow import compile_database_design_graph

            result = compile_database_design_graph().invoke(
                {
                    "requirement_json_path": uploaded_req_path or requirement_path,
                    "erd_docx_path": uploaded_erd_path or erd_docx_path,
                    "use_rag": use_rag,
                    "output_json_path": output_json_path,
                    "output_docx_path": output_docx_path,
                }
            )

        if result.get("status") != "VALID":
            st.error("DB 설계서 생성 실패")
            st.write(result.get("validation_errors", []))
            return
        st.success("DB 설계서 생성 완료")
        _show_result_paths(
            result,
            [("output_json_path", "DB 설계 JSON"), ("database_design_docx_path", "DB 설계 DOCX")],
        )
        _load_json_preview(result.get("output_json_path"))


def render_srs_tab() -> None:
    st.subheader("SRS 요구사항 정의서 생성/수정")
    mode = st.radio("실행 모드", ["신규 생성", "수정"], horizontal=True, key="srs_mode")
    save_docx = st.checkbox("DOCX 생성", value=True, key="srs_save_docx")
    output_json_path = st.text_input(
        "출력 JSON 경로",
        value=f"./json_temp/srs_agent_output_{_timestamp()}.json",
        key="srs_output_json",
    )
    output_reqs_path = st.text_input(
        "final_reqs 출력 경로",
        value=f"./json_temp/srs_final_reqs_{_timestamp()}.json",
        key="srs_output_reqs",
    )

    if mode == "신규 생성":
        rfp_upload = st.file_uploader("RFP 분석 JSON 업로드", type=["json"], key="srs_rfp_upload")
        minutes_upload = st.file_uploader("회의록 TXT 업로드", type=["txt"], key="srs_minutes_upload")
        rfp_json_path = st.text_input(
            "RFP 분석 JSON 경로",
            value="./data/requirement_sources/서민금융진흥원 AI기반 통합 플랫폼 구축 사업 제안요청서_final.json",
            key="srs_rfp_path",
        )
        minutes_path = st.text_input(
            "회의록 TXT 경로",
            value="./data/requirement_sources/meeting_minutes/RFP_변경_회의록.txt",
            key="srs_minutes_path",
        )

        if st.button("SRS 신규 생성 실행", type="primary", key="run_srs_generate"):
            uploaded_rfp_path = _save_uploaded_file(rfp_upload, "srs_rfp")
            uploaded_minutes_path = _save_uploaded_file(minutes_upload, "srs_minutes")
            args = SimpleNamespace(
                rfp_json_path=uploaded_rfp_path or rfp_json_path,
                minutes_path=uploaded_minutes_path or minutes_path,
                output_json_path=output_json_path,
                output_reqs_path=output_reqs_path,
                save_docx=save_docx,
            )
            with st.spinner("SRS 신규 생성 중입니다..."):
                from main_generate_srs import generate_mode

                generate_mode(args)
            st.success("SRS 신규 생성 완료")
            st.write(f"SRS JSON: `{output_json_path}`")
            st.write(f"final_reqs: `{output_reqs_path}`")
            _download_file(output_json_path, "SRS JSON")
            _download_file(output_reqs_path, "SRS final_reqs")
            _load_json_preview(output_json_path)

    else:
        existing_upload = st.file_uploader("기존 SRS 요구사항 JSON 업로드", type=["json"], key="srs_existing_upload")
        existing_reqs_path = st.text_input(
            "기존 SRS 요구사항 JSON 경로",
            value="./json_temp/srs_agent_output.json",
            key="srs_existing_path",
        )
        instruction = st.text_area("수정 지시", height=160, key="srs_instruction")
        instruction_file = st.file_uploader("수정 지시 TXT 업로드", type=["txt"], key="srs_instruction_file")

        if st.button("SRS 수정 실행", type="primary", key="run_srs_modify"):
            uploaded_existing_path = _save_uploaded_file(existing_upload, "srs_existing")
            uploaded_instruction_path = _save_uploaded_file(instruction_file, "srs_instruction")
            args = SimpleNamespace(
                existing_reqs_path=uploaded_existing_path or existing_reqs_path,
                instruction=instruction.strip() or None,
                instruction_file=uploaded_instruction_path,
                output_json_path=output_json_path,
                output_reqs_path=output_reqs_path,
                save_docx=save_docx,
            )
            with st.spinner("SRS 수정 중입니다..."):
                from main_generate_srs import modify_mode

                modify_mode(args)
            st.success("SRS 수정 완료")
            st.write(f"SRS JSON: `{output_json_path}`")
            st.write(f"final_reqs: `{output_reqs_path}`")
            _download_file(output_json_path, "SRS 수정 JSON")
            _download_file(output_reqs_path, "SRS final_reqs")
            _load_json_preview(output_json_path)


def render_arch_tab() -> None:
    st.subheader("아키텍처 설계서 생성")
    requirement_upload = st.file_uploader("요구사항 JSON 업로드", type=["json"], key="arch_req_upload")
    infra_upload = st.file_uploader("인프라 스펙 JSON 업로드", type=["json"], key="arch_infra_upload")

    requirement_path = st.text_input(
        "요구사항 JSON 경로",
        value="./data/requirements/requirement.json",
        key="arch_req_path",
    )
    infra_spec_path = st.text_input(
        "인프라 스펙 JSON 경로",
        value="./data/architecture/infra_spec.json",
        key="arch_infra_path",
    )
    render_image = st.checkbox("Mermaid PNG 생성", value=True, key="arch_render_image")
    output_json_path = st.text_input(
        "출력 JSON 경로",
        value=f"./json_temp/architecture_agent_output_{_timestamp()}.json",
        key="arch_output_json",
    )
    output_md_path = st.text_input(
        "출력 Markdown 경로",
        value=f"./output/architecture_report_{_timestamp()}.md",
        key="arch_output_md",
    )
    output_docx_path = st.text_input(
        "출력 DOCX 경로",
        value=f"./output/architecture_report_{_timestamp()}.docx",
        key="arch_output_docx",
    )
    output_image_path = st.text_input(
        "출력 이미지 경로",
        value=f"./output/architecture_diagram_{_timestamp()}.png",
        key="arch_output_image",
    )

    if st.button("아키텍처 설계서 생성 실행", type="primary", key="run_arch"):
        uploaded_req_path = _save_uploaded_file(requirement_upload, "arch_requirement")
        uploaded_infra_path = _save_uploaded_file(infra_upload, "arch_infra")
        initial_state = {
            "requirement_json_path": uploaded_req_path or requirement_path,
            "infra_spec_path": uploaded_infra_path or infra_spec_path,
            "render_image": render_image,
            "output_json_path": output_json_path,
            "output_md_path": output_md_path,
            "output_docx_path": output_docx_path,
            "output_image_path": output_image_path,
        }
        with st.spinner("아키텍처 설계서 생성 중입니다..."):
            from workflows.architecture_workflow import compile_architecture_graph

            result = compile_architecture_graph().invoke(initial_state)

        if result.get("status") != "VALID":
            st.error("아키텍처 설계서 생성 실패")
            st.write(result.get("validation_result", {}))
            return
        st.success("아키텍처 설계서 생성 완료")
        _show_result_paths(
            result,
            [
                ("output_json_path", "아키텍처 JSON"),
                ("output_md_path", "아키텍처 Markdown"),
                ("output_docx_path", "아키텍처 DOCX"),
                ("output_image_path", "아키텍처 이미지"),
            ],
        )
        _load_json_preview(result.get("output_json_path"))


def render_ts_tab() -> None:
    st.subheader("통합시험 시나리오 생성")
    requirement_upload = st.file_uploader("요구사항 JSON 업로드", type=["json"], key="ts_req_upload")
    ui_uploads = st.file_uploader(
        "UI 설계서 JSON 업로드",
        type=["json"],
        accept_multiple_files=True,
        key="ts_ui_uploads",
    )
    requirement_path = st.text_input(
        "요구사항 JSON 경로",
        value="./data/requirements/requirement.json",
        key="ts_req_path",
    )
    ui_paths_text = st.text_area(
        "UI 설계서 JSON 경로 목록",
        value="",
        height=90,
        help="여러 개면 줄바꿈으로 입력합니다.",
        key="ts_ui_paths",
    )
    max_retries = st.number_input("요구사항별 재시도 횟수", min_value=0, max_value=5, value=1, step=1)
    output_json_path = st.text_input(
        "출력 JSON 경로",
        value=f"./json_temp/ts_agent_output_{_timestamp()}.json",
        key="ts_output_json",
    )
    output_docx_path = st.text_input(
        "출력 DOCX 경로",
        value=f"./output/integration_test_scenario_{_timestamp()}.docx",
        key="ts_output_docx",
    )

    if st.button("통합시험 시나리오 생성 실행", type="primary", key="run_ts"):
        uploaded_req_path = _save_uploaded_file(requirement_upload, "ts_requirement")
        uploaded_ui_paths = _save_uploaded_files(ui_uploads, "ts_ui")
        typed_ui_paths = [line.strip() for line in ui_paths_text.splitlines() if line.strip()]

        with st.spinner("통합시험 시나리오 생성 중입니다..."):
            from workflows.ts_workflow import compile_ts_graph

            result = compile_ts_graph().invoke(
                {
                    "requirement_json_path": uploaded_req_path or requirement_path,
                    "ui_paths": uploaded_ui_paths + typed_ui_paths,
                    "output_json_path": output_json_path,
                    "output_docx_path": output_docx_path,
                    "max_retries": int(max_retries),
                }
            )

        if result.get("status") != "VALID":
            st.error("통합시험 시나리오 생성 실패")
            return
        st.success("통합시험 시나리오 생성 완료")
        st.write("요약:", result.get("summary", {}))
        _show_result_paths(result, [("output_json_path", "TS JSON"), ("output_docx_path", "TS DOCX")])
        _load_json_preview(result.get("output_json_path"))


def main() -> None:
    st.set_page_config(page_title="ALPLED 산출물 Agent Runner", layout="wide")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_TEMP_DIR.mkdir(parents=True, exist_ok=True)

    st.title("ALPLED 산출물 Agent Runner")
    st.caption("ERD, DB 설계서, SRS, 아키텍처 설계서, 통합시험 시나리오를 같은 화면에서 실행합니다.")

    with st.sidebar:
        st.header("실행 전 확인")
        st.write("`.env`의 LLM/Qdrant 설정을 사용합니다.")
        st.code(
            "streamlit run streamlit_app.py",
            language="powershell",
        )
        st.write(f"작업 폴더: `{ROOT_DIR}`")

    tabs = st.tabs(["ERD", "DB 설계서", "SRS", "아키텍처", "통합시험 TS"])
    with tabs[0]:
        render_erd_tab()
    with tabs[1]:
        render_db_tab()
    with tabs[2]:
        render_srs_tab()
    with tabs[3]:
        render_arch_tab()
    with tabs[4]:
        render_ts_tab()


if __name__ == "__main__":
    main()
