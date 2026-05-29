import json
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


def _docx_output_path(title: str, subdir: str | None = None) -> str:
    output_dir = "./output" if subdir is None else f"./output/{subdir}"
    return f"{output_dir}/{title}_{_timestamp()}.docx"


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


def _input_priority_note(default_target: str = "아래 기본 경로") -> None:
    st.info(f"파일을 업로드하면 업로드한 파일로 실행합니다. 업로드하지 않으면 {default_target}를 사용합니다.")


def render_erd_tab() -> None:
    st.subheader("엔티티 관계 모형 설계서 생성")
    _input_priority_note("아래 요구사항 JSON 기본 경로")
    requirement_upload = st.file_uploader("요구사항 JSON 업로드", type=["json"], key="erd_req_upload")
    requirement_path = st.text_input(
        "요구사항 JSON 기본 경로 (업로드 없을 때 사용)",
        value="./data/requirements/requirement.json",
        key="erd_req_path",
    )

    col1, col2 = st.columns(2)
    with col1:
        use_llm = st.checkbox("LLM 사용", value=True, key="erd_use_llm")
    with col2:
        use_mermaid = st.checkbox("Mermaid 포함", value=True, key="erd_use_mermaid")

    output_json_path = st.text_input(
        "출력 JSON 경로",
        value=f"./json_temp/erd_agent_output_{_timestamp()}.json",
        key="erd_output_json",
    )
    output_docx_path = st.text_input(
        "출력 DOCX 경로",
        value=_docx_output_path("엔티티 관계 모형 설계서"),
        key="erd_output_docx",
    )

    if st.button("엔티티 관계 모형 설계서 생성 실행", type="primary", key="run_erd"):
        uploaded_path = _save_uploaded_file(requirement_upload, "erd_requirement")
        with st.spinner("ERD 생성 중입니다..."):
            from workflows.erd_workflow import compile_erd_graph

            result = compile_erd_graph().invoke(
                {
                    "requirement_json_path": uploaded_path or requirement_path,
                    "use_llm": use_llm,
                    "use_mermaid": use_mermaid,
                    "fast_table": False,
                    "output_json_path": output_json_path,
                    "output_docx_path": output_docx_path,
                }
            )

        if result.get("status") != "VALID":
            st.error("ERD 생성 실패")
            st.write(result.get("validation_errors", []))
            return
        st.success("엔티티 관계 모형 설계서 생성 완료")
        _show_result_paths(result, [("output_json_path", "엔티티 관계 모형 JSON"), ("erd_docx_path", "엔티티 관계 모형 설계서 DOCX")])
        _load_json_preview(result.get("output_json_path"))


def render_db_tab() -> None:
    st.subheader("데이터베이스 설계서 생성")
    _input_priority_note("아래 요구사항/ERD 기본 경로")
    requirement_upload = st.file_uploader("요구사항 JSON 업로드", type=["json"], key="db_req_upload")
    erd_upload = st.file_uploader("엔티티 관계 모형 설계서 DOCX 업로드", type=["docx"], key="db_erd_upload")

    requirement_path = st.text_input(
        "요구사항 JSON 기본 경로 (업로드 없을 때 사용)",
        value="./data/requirements/requirement.json",
        key="db_req_path",
    )
    erd_docx_path = st.text_input(
        "엔티티 관계 모형 설계서 DOCX 기본 경로 (업로드 없을 때 사용)",
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
        value=_docx_output_path("데이터베이스 설계서"),
        key="db_output_docx",
    )

    if st.button("데이터베이스 설계서 생성 실행", type="primary", key="run_db"):
        uploaded_req_path = _save_uploaded_file(requirement_upload, "db_requirement")
        uploaded_erd_path = _save_uploaded_file(erd_upload, "db_erd")
        with st.spinner("데이터베이스 설계서 생성 중입니다..."):
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
            st.error("데이터베이스 설계서 생성 실패")
            st.write(result.get("validation_errors", []))
            return
        st.success("데이터베이스 설계서 생성 완료")
        _show_result_paths(
            result,
            [("output_json_path", "데이터베이스 설계 JSON"), ("database_design_docx_path", "데이터베이스 설계서 DOCX")],
        )
        _load_json_preview(result.get("output_json_path"))


def render_srs_tab() -> None:
    st.subheader("사용자 요구사항 정의서 생성/수정")
    mode = st.radio("실행 모드", ["신규 생성", "수정"], horizontal=True, key="srs_mode")
    save_docx = st.checkbox("DOCX 생성", value=True, key="srs_save_docx")
    st.caption(
        "DOCX 생성 시 아래 `출력 DOCX 경로`에 저장됩니다."
    )
    output_json_path = st.text_input(
        "출력 JSON 경로",
        value=f"./json_temp/srs_agent_output_{_timestamp()}.json",
        key="srs_output_json",
    )
    output_reqs_path = st.text_input(
        "final_reqs 출력 경로",
        value="./output/final_reqs.json",
        key="srs_output_reqs",
    )
    output_review_path = st.text_input(
        "review_reqs 출력 경로",
        value="./output/review_reqs.json",
        key="srs_output_review_reqs",
    )
    output_docx_path = st.text_input(
        "출력 DOCX 경로",
        value=_docx_output_path("사용자 요구사항 정의서"),
        key="srs_output_docx",
    )

    if mode == "신규 생성":
        _input_priority_note("아래 RFP/회의록 기본 경로")
        rfp_upload = st.file_uploader(
            "RFP 원문 또는 분석 JSON 업로드",
            type=["pdf", "docx", "txt", "md", "json"],
            key="srs_rfp_upload",
        )
        minutes_upload = st.file_uploader("회의록 TXT 업로드", type=["txt"], key="srs_minutes_upload")
        rfp_json_path = st.text_input(
            "RFP 분석 JSON 기본 경로 (업로드 없을 때 사용)",
            value="./data/requirement_sources/서민금융진흥원 AI기반 통합 플랫폼 구축 사업 제안요청서_final.json",
            key="srs_rfp_path",
        )
        extract_rfp_if_needed = st.checkbox(
            "원문 RFP 업로드 시 요구사항 JSON 자동 추출",
            value=True,
            key="srs_extract_rfp_if_needed",
        )
        rfp_extract_output_path = st.text_input(
            "RFP 추출 JSON 저장 경로",
            value=f"./json_temp/srs_rfp_extracted_{_timestamp()}.json",
            key="srs_rfp_extract_output_path",
        )
        minutes_path = st.text_input(
            "회의록 TXT 기본 경로 (업로드 없을 때 사용)",
            value="./data/requirement_sources/meeting_minutes/RFP_변경_회의록.txt",
            key="srs_minutes_path",
        )

        with st.expander("회의록 먼저 생성", expanded=False):
            _input_priority_note("아래 회의록 생성용 RFP 기본 경로")
            raw_rfp_upload = st.file_uploader(
                "회의록 생성용 RFP 원문 업로드",
                type=["pdf", "docx", "txt", "md", "json"],
                key="srs_minutes_rfp_upload",
            )
            raw_rfp_path = st.text_input(
                "회의록 생성용 RFP 원문 기본 경로 (업로드 없을 때 사용)",
                value="./data/requirement_sources/RFP/서민금융진흥원 AI기반 통합 플랫폼 구축 사업 제안요청서.pdf",
                key="srs_minutes_rfp_path",
            )
            minutes_type = st.radio(
                "회의록 종류",
                ["변경 회의록", "착수 회의록"],
                horizontal=True,
                key="srs_minutes_type",
            )
            provider = st.selectbox(
                "생성 모델",
                ["OpenAI API", "현재 .env LLM"],
                key="srs_minutes_provider",
            )
            openai_model = st.text_input(
                "OpenAI 모델명",
                value="gpt-4.1-mini",
                key="srs_minutes_openai_model",
            )
            max_rfp_chars = st.number_input(
                "RFP 입력 최대 글자 수",
                min_value=1000,
                max_value=30000,
                value=8000,
                step=1000,
                key="srs_minutes_max_chars",
            )
            minutes_output_path = st.text_input(
                "생성 회의록 저장 경로",
                value="./data/requirement_sources/meeting_minutes/RFP_변경_회의록.txt",
                key="srs_minutes_output_path",
            )

            if st.button("회의록 생성 실행", key="run_srs_minutes"):
                uploaded_raw_rfp_path = _save_uploaded_file(raw_rfp_upload, "srs_minutes_rfp")
                with st.spinner("회의록 생성 중입니다..."):
                    from services.minutes_generator import generate_minutes

                    saved_minutes_path = generate_minutes(
                        uploaded_raw_rfp_path or raw_rfp_path,
                        minutes_output_path,
                        minutes_type="change" if minutes_type == "변경 회의록" else "kickoff",
                        provider="openai" if provider == "OpenAI API" else "common_llm",
                        model=openai_model.strip() or None,
                        max_rfp_chars=int(max_rfp_chars),
                        existing_requirements_path=output_reqs_path,
                    )
                st.success("회의록 생성 완료")
                st.write(f"회의록 TXT: `{saved_minutes_path}`")
                _download_file(saved_minutes_path, "회의록 TXT")
                with st.expander("회의록 미리보기", expanded=True):
                    st.text(Path(saved_minutes_path).read_text(encoding="utf-8")[:5000])

        if st.button("사용자 요구사항 정의서 신규 생성 실행", type="primary", key="run_srs_generate"):
            uploaded_rfp_path = _save_uploaded_file(rfp_upload, "srs_rfp")
            uploaded_minutes_path = _save_uploaded_file(minutes_upload, "srs_minutes")
            resolved_rfp_path = uploaded_rfp_path or rfp_json_path

            if uploaded_rfp_path and Path(uploaded_rfp_path).suffix.lower() != ".json" and extract_rfp_if_needed:
                with st.spinner("RFP 원문에서 요구사항 JSON 추출 중입니다..."):
                    from services.rfp_extractor import extract_rfp_to_json

                    resolved_rfp_path = extract_rfp_to_json(
                        uploaded_rfp_path,
                        rfp_extract_output_path,
                        use_llm=True,
                    )
                st.write(f"RFP 추출 JSON: `{resolved_rfp_path}`")
                _download_file(resolved_rfp_path, "RFP 추출 JSON")

            args = SimpleNamespace(
                rfp_json_path=resolved_rfp_path,
                minutes_path=uploaded_minutes_path or minutes_path,
                output_json_path=output_json_path,
                output_reqs_path=output_reqs_path,
                output_review_path=output_review_path,
                output_docx_path=output_docx_path,
                save_docx=save_docx,
            )
            with st.spinner("SRS 신규 생성 중입니다..."):
                from main_generate_srs import generate_mode

                try:
                    result = generate_mode(args)
                except Exception as e:
                    st.error("사용자 요구사항 정의서 생성 실패")
                    st.exception(e)
                    return
            st.success("사용자 요구사항 정의서 신규 생성 완료")
            st.write(
                f"생성 요구사항: `{len(result.get('final_reqs', []))}`건 / "
                f"검토 필요: `{len(result.get('review_reqs', []))}`건"
            )
            st.write(f"SRS JSON: `{output_json_path}`")
            st.write(f"final_reqs: `{output_reqs_path}`")
            st.write(f"review_reqs: `{output_review_path}`")
            if result.get("docx_path"):
                st.write(f"사용자 요구사항 정의서 DOCX 저장 위치: `{result['docx_path']}`")
                _download_file(result["docx_path"], "사용자 요구사항 정의서 DOCX")
            elif save_docx:
                st.warning("final_reqs가 비어 있어 DOCX를 생성하지 않았습니다. 생성 성공 시 `./output/generated_YYYYMMDD_HHMMSS.docx`에 저장됩니다.")
            _download_file(output_json_path, "사용자 요구사항 정의서 JSON")
            _download_file(output_reqs_path, "사용자 요구사항 정의서 final_reqs")
            _download_file(output_review_path, "사용자 요구사항 정의서 review_reqs")
            _load_json_preview(output_json_path)

    else:
        _input_priority_note("아래 기존 SRS 요구사항 기본 경로")
        existing_upload = st.file_uploader("기존 SRS 요구사항 JSON 업로드", type=["json"], key="srs_existing_upload")
        existing_reqs_path = st.text_input(
            "기존 SRS 요구사항 JSON 기본 경로 (업로드 없을 때 사용)",
            value="./output/final_reqs.json",
            key="srs_existing_path",
        )
        instruction = st.text_area("수정 지시", height=160, key="srs_instruction")
        instruction_file = st.file_uploader("수정 지시 TXT 업로드", type=["txt"], key="srs_instruction_file")

        if st.button("사용자 요구사항 정의서 수정 실행", type="primary", key="run_srs_modify"):
            uploaded_existing_path = _save_uploaded_file(existing_upload, "srs_existing")
            uploaded_instruction_path = _save_uploaded_file(instruction_file, "srs_instruction")
            args = SimpleNamespace(
                existing_reqs_path=uploaded_existing_path or existing_reqs_path,
                instruction=instruction.strip() or None,
                instruction_file=uploaded_instruction_path,
                output_json_path=output_json_path,
                output_reqs_path=output_reqs_path,
                output_review_path=output_review_path,
                output_docx_path=output_docx_path,
                save_docx=save_docx,
            )
            with st.spinner("SRS 수정 중입니다..."):
                from main_generate_srs import modify_mode

                try:
                    result = modify_mode(args)
                except Exception as e:
                    st.error("사용자 요구사항 정의서 수정 실패")
                    st.exception(e)
                    return
            st.success("사용자 요구사항 정의서 수정 완료")
            st.write(
                f"수정 요구사항: `{len(result.get('final_reqs', []))}`건 / "
                f"검토 필요: `{len(result.get('review_reqs', []))}`건"
            )
            st.write(f"SRS JSON: `{output_json_path}`")
            st.write(f"final_reqs: `{output_reqs_path}`")
            st.write(f"review_reqs: `{output_review_path}`")
            if result.get("docx_path"):
                st.write(f"사용자 요구사항 정의서 DOCX 저장 위치: `{result['docx_path']}`")
                _download_file(result["docx_path"], "사용자 요구사항 정의서 DOCX")
            elif save_docx:
                st.warning("final_reqs가 비어 있어 DOCX를 생성하지 않았습니다. 생성 성공 시 `./output/modified_YYYYMMDD_HHMMSS.docx`에 저장됩니다.")
            _download_file(output_json_path, "사용자 요구사항 정의서 수정 JSON")
            _download_file(output_reqs_path, "사용자 요구사항 정의서 final_reqs")
            _download_file(output_review_path, "사용자 요구사항 정의서 review_reqs")
            _load_json_preview(output_json_path)


def render_ui_design_tab() -> None:
    st.subheader("사용자 인터페이스 설계서 생성")
    _input_priority_note("아래 사용자 요구사항/프로토타입 기본 경로 또는 폴더")
    requirement_uploads = st.file_uploader(
        "사용자 요구사항 JSON 업로드",
        type=["json"],
        accept_multiple_files=True,
        key="ui_req_uploads",
    )
    image_uploads = st.file_uploader(
        "프로토타입 이미지 업로드",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key="ui_image_uploads",
    )
    requirement_path = st.text_input(
        "사용자 요구사항 JSON 기본 경로/폴더 (업로드 없을 때 사용)",
        value="./data/interface/requirements",
        key="ui_req_path",
    )
    image_path = st.text_input(
        "프로토타입 이미지 기본 경로/폴더 (업로드 없을 때 사용)",
        value="./data/interface/prototypes",
        key="ui_image_path",
    )
    max_images = st.number_input(
        "처리할 이미지 수",
        min_value=1,
        max_value=50,
        value=1,
        step=1,
        key="ui_max_images",
    )
    all_images = st.checkbox("전체 이미지 처리", value=False, key="ui_all_images")
    work_dir = st.text_input(
        "작업 JSON/모델 원문 저장 폴더",
        value="./json_temp/interface",
        key="ui_work_dir",
    )
    output_json_path = st.text_input(
        "출력 통합 JSON 경로",
        value=f"./json_temp/interface/ui_design_integrated_{_timestamp()}.json",
        key="ui_output_json",
    )
    output_docx_path = st.text_input(
        "출력 DOCX 경로",
        value=_docx_output_path("사용자 인터페이스 설계서", "interface"),
        key="ui_output_docx",
    )

    if st.button("사용자 인터페이스 설계서 생성 실행", type="primary", key="run_ui_design"):
        uploaded_req_paths = _save_uploaded_files(requirement_uploads, "ui_requirement")
        uploaded_image_paths = _save_uploaded_files(image_uploads, "ui_prototype")
        with st.spinner("사용자 인터페이스 설계서 생성 중입니다..."):
            from workflows.interface_workflow import compile_interface_graph

            result = compile_interface_graph().invoke(
                {
                    "requirement_paths": uploaded_req_paths or requirement_path,
                    "image_paths": uploaded_image_paths or image_path,
                    "output_json_path": output_json_path,
                    "output_docx_path": output_docx_path,
                    "work_dir": work_dir,
                    "max_images": None if all_images else int(max_images),
                }
            )

        if result.get("status") != "VALID":
            st.error("사용자 인터페이스 설계서 생성 실패")
            return
        st.success("사용자 인터페이스 설계서 생성 완료")
        st.write(f"화면 수: `{len(result.get('screen_specs', []))}`")
        _show_result_paths(
            result,
            [("output_json_path", "사용자 인터페이스 설계서 JSON"), ("output_docx_path", "사용자 인터페이스 설계서 DOCX")],
        )
        _load_json_preview(result.get("output_json_path"))


def render_arch_tab() -> None:
    st.subheader("아키텍처 설계서 생성")
    _input_priority_note("아래 요구사항/인프라 스펙 기본 경로")
    requirement_upload = st.file_uploader("요구사항 JSON 업로드", type=["json"], key="arch_req_upload")
    infra_upload = st.file_uploader("인프라 스펙 JSON 업로드", type=["json"], key="arch_infra_upload")

    requirement_path = st.text_input(
        "요구사항 JSON 기본 경로 (업로드 없을 때 사용)",
        value="./data/architecture/architecture_requirements.json",
        key="arch_req_path",
    )
    infra_spec_path = st.text_input(
        "인프라 스펙 JSON 기본 경로 (업로드 없을 때 사용)",
        value="./data/architecture/infra_spec.json",
        key="arch_infra_path",
    )
    render_image = st.checkbox("Mermaid PNG 생성", value=True, key="arch_render_image")
    output_json_path = st.text_input(
        "출력 JSON 경로",
        value=f"./json_temp/architecture_agent_output_{_timestamp()}.json",
        key="arch_output_json",
    )
    output_docx_path = st.text_input(
        "출력 DOCX 경로",
        value=_docx_output_path("아키텍처 설계서"),
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
            "output_docx_path": output_docx_path,
            "output_image_path": output_image_path,
        }
        with st.spinner("아키텍처 설계서 생성 중입니다..."):
            from workflows.architecture_workflow import compile_architecture_graph

            result = compile_architecture_graph().invoke(initial_state)

        st.session_state["arch_last_result"] = result

    result = st.session_state.get("arch_last_result")
    if result:
        if result.get("status") != "VALID":
            st.error("아키텍처 설계서 생성 실패")
            st.write(result.get("validation_result", {}))
            return
        st.success("아키텍처 설계서 생성 완료")
        _show_result_paths(
            result,
            [
                ("output_json_path", "아키텍처 JSON"),
                ("output_docx_path", "아키텍처 설계서 DOCX"),
                ("output_image_path", "아키텍처 이미지"),
            ],
        )
        _load_json_preview(result.get("output_json_path"))


def render_ts_tab() -> None:
    st.subheader("통합 시험 시나리오 생성")
    _input_priority_note("아래 요구사항/UI 설계서 기본 경로")
    requirement_upload = st.file_uploader("요구사항 JSON 업로드", type=["json"], key="ts_req_upload")
    ui_uploads = st.file_uploader(
        "UI 설계서 JSON 업로드",
        type=["json"],
        accept_multiple_files=True,
        key="ts_ui_uploads",
    )
    requirement_path = st.text_input(
        "요구사항 JSON 기본 경로 (업로드 없을 때 사용)",
        value="./data/requirements/requirement.json",
        key="ts_req_path",
    )
    ui_paths_text = st.text_area(
        "UI 설계서 JSON 기본 경로 목록 (업로드 없을 때 추가 사용)",
        value="",
        height=90,
        help="여러 개면 줄바꿈으로 입력합니다.",
        key="ts_ui_paths",
    )
    max_retries = st.number_input("요구사항별 재시도 횟수", min_value=0, max_value=5, value=0, step=1)
    output_json_path = st.text_input(
        "출력 JSON 경로",
        value=f"./json_temp/ts_agent_output_{_timestamp()}.json",
        key="ts_output_json",
    )
    output_docx_path = st.text_input(
        "출력 DOCX 경로",
        value=_docx_output_path("통합 시험 시나리오"),
        key="ts_output_docx",
    )

    if st.button("통합 시험 시나리오 생성 실행", type="primary", key="run_ts"):
        uploaded_req_path = _save_uploaded_file(requirement_upload, "ts_requirement")
        uploaded_ui_paths = _save_uploaded_files(ui_uploads, "ts_ui")
        typed_ui_paths = [line.strip() for line in ui_paths_text.splitlines() if line.strip()]

        with st.spinner("통합 시험 시나리오 생성 중입니다..."):
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
            st.error("통합 시험 시나리오 생성 실패")
            st.write(result.get("validation_errors", []))
            _show_result_paths(result, [("output_json_path", "통합 시험 시나리오 JSON")])
            return
        st.success("통합 시험 시나리오 생성 완료")
        st.write("요약:", result.get("summary", {}))
        _show_result_paths(result, [("output_json_path", "통합 시험 시나리오 JSON"), ("output_docx_path", "통합 시험 시나리오 DOCX")])
        _load_json_preview(result.get("output_json_path"))


def main() -> None:
    st.set_page_config(page_title="ALPLED 산출물 Agent Runner", layout="wide")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_TEMP_DIR.mkdir(parents=True, exist_ok=True)

    st.title("ALPLED 산출물 Agent Runner")
    st.caption("엔티티 관계 모형 설계서, 사용자 요구사항 정의서, 사용자 인터페이스 설계서, 아키텍처 설계서, 통합 시험 시나리오, 데이터베이스 설계서를 같은 화면에서 실행합니다.")

    tabs = st.tabs([
        "사용자 요구사항 정의서",
        "사용자 인터페이스 설계서",
        "아키텍처 설계서",
        "엔티티 관계 모형 설계서",
        "데이터베이스 설계서",
        "통합 시험 시나리오",
    ])
    with tabs[0]:
        render_srs_tab()
    with tabs[1]:
        render_ui_design_tab()
    with tabs[2]:
        render_arch_tab()
    with tabs[3]:
        render_erd_tab()
    with tabs[4]:
        render_db_tab()
    with tabs[5]:
        render_ts_tab()


if __name__ == "__main__":
    main()
