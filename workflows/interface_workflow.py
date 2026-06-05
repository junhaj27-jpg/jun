import json
import traceback
from pathlib import Path

from langgraph.graph import END, START, StateGraph
from PIL import Image

from agents.interface_agent import analysis as interface_analysis
from agents.interface_agent.analysis import analyze_screen_image, generate_ui_structure
from agents.interface_agent.config import (
    OUTPUT_DOCX_PATH,
    PROTOTYPE_DIR,
    REQUIREMENT_DIR,
    WORK_DIR,
)
from agents.interface_agent.extractors import (
    collect_image_paths,
    collect_requirement_json_paths,
    ensure_docx_output_path,
    load_requirement_summary_json,
)
from generators.interface_docx_generator import (
    create_ui_design_docx,
    save_integrated_ui_design_json,
)
from workflows.interface_state import InterfaceWorkflowState


def _work_dir(state: InterfaceWorkflowState) -> Path:
    return Path(state.get("work_dir") or WORK_DIR)

# 요구사항 JSON, 프로토타입 이미지 로드 
def load_interface_inputs_node(state: InterfaceWorkflowState) -> InterfaceWorkflowState:
    requirement_paths = state.get("requirement_paths") or REQUIREMENT_DIR
    image_paths = state.get("image_paths") or PROTOTYPE_DIR
    max_images = state.get("max_images")

    requirement_file_paths = collect_requirement_json_paths(requirement_paths)
    image_file_paths = collect_image_paths(image_paths)
    if max_images is not None:
        if int(max_images) < 1:
            raise ValueError("max_images는 1 이상이어야 합니다.")
        image_file_paths = image_file_paths[: int(max_images)]

    requirement_summary = load_requirement_summary_json(requirement_file_paths)

    for image_path in image_file_paths:
        try:
            with Image.open(image_path) as img:
                img.verify()
        except Exception as exc:
            raise RuntimeError(f"이미지 파일을 열 수 없습니다: {image_path}") from exc

    work_dir = _work_dir(state)
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "requirement_summary.json").write_text(
        json.dumps(requirement_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "requirement_summary": requirement_summary,
        "image_file_paths": [str(path) for path in image_file_paths],
        "work_dir": str(work_dir),
    }


# 프로토타입 이미지 분석 
def analyze_interface_screens_node(state: InterfaceWorkflowState) -> InterfaceWorkflowState:
    work_dir = _work_dir(state)
    interface_analysis.WORK_DIR = work_dir

    screen_specs = []
    failures = []
    for idx, image_path_text in enumerate(state.get("image_file_paths", []), start=1):
        image_path = Path(image_path_text)
        try:
            screen_specs.append(analyze_screen_image(image_path, state.get("requirement_summary", {}), idx))
        except Exception as exc:
            print("분석 실패:", image_path)
            traceback.print_exc()
            failures.append(f"{image_path.name}: {type(exc).__name__}: {str(exc)[:500]}")

    if not screen_specs:
        detail = "\n".join(failures) if failures else "처리할 이미지 경로가 비어 있습니다."
        raise RuntimeError("분석된 화면이 없습니다. 원인:\n" + detail)

    weak_specs = [
        spec.get("image_path") or spec.get("screen_name") or spec.get("screen_id")
        for spec in screen_specs
        if len(spec.get("process_contents", []) or []) < 2
    ]
    if weak_specs:
        raise RuntimeError(
            "처리내용이 부족한 화면이 있어 빈 DOCX 생성을 중단합니다: "
            + ", ".join(str(item) for item in weak_specs)
        )

    (work_dir / "screen_specs.json").write_text(
        json.dumps(screen_specs, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"screen_specs": screen_specs}


# UI 구조 생성 
def generate_interface_structure_node(state: InterfaceWorkflowState) -> InterfaceWorkflowState:
    work_dir = _work_dir(state)
    ui_structure = generate_ui_structure(state.get("screen_specs", []))
    (work_dir / "ui_structure.json").write_text(
        json.dumps(ui_structure, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"ui_structure": ui_structure}


# 통합 UI 디자인 JSON 저장
def save_interface_json_node(state: InterfaceWorkflowState) -> InterfaceWorkflowState:
    output_docx_path = ensure_docx_output_path(Path(state.get("output_docx_path") or OUTPUT_DOCX_PATH))
    output_json_path = Path(state.get("output_json_path") or (_work_dir(state) / "ui_design_integrated.json"))

    integrated_json_path = save_integrated_ui_design_json(
        requirement_summary=state.get("requirement_summary", {}),
        ui_structure=state.get("ui_structure", []),
        screen_specs=state.get("screen_specs", []),
        output_docx_path=output_docx_path,
        output_json_path=output_json_path,
    )
    return {
        "output_docx_path": str(output_docx_path),
        "output_json_path": str(output_json_path),
        "integrated_json_path": str(integrated_json_path),
    }


# DOCX 생성
def generate_interface_docx_node(state: InterfaceWorkflowState) -> InterfaceWorkflowState:
    output_docx_path = create_ui_design_docx(
        requirement_summary=state.get("requirement_summary", {}),
        ui_structure=state.get("ui_structure", []),
        screen_specs=state.get("screen_specs", []),
        output_path=Path(state.get("output_docx_path") or OUTPUT_DOCX_PATH),
    )
    if not Path(output_docx_path).exists():
        raise RuntimeError(f"DOCX 저장 실패: {output_docx_path}")
    return {"output_docx_path": str(output_docx_path), "status": "VALID"}


# 노드 연결
def compile_interface_graph():
    workflow = StateGraph(InterfaceWorkflowState)

    workflow.add_node("load_interface_inputs_node", load_interface_inputs_node)
    workflow.add_node("analyze_interface_screens_node", analyze_interface_screens_node)
    workflow.add_node("generate_interface_structure_node", generate_interface_structure_node)
    workflow.add_node("save_interface_json_node", save_interface_json_node)
    workflow.add_node("generate_interface_docx_node", generate_interface_docx_node)

    workflow.add_edge(START, "load_interface_inputs_node")
    workflow.add_edge("load_interface_inputs_node", "analyze_interface_screens_node")
    workflow.add_edge("analyze_interface_screens_node", "generate_interface_structure_node")
    workflow.add_edge("generate_interface_structure_node", "save_interface_json_node")
    workflow.add_edge("save_interface_json_node", "generate_interface_docx_node")
    workflow.add_edge("generate_interface_docx_node", END)

    return workflow.compile()
