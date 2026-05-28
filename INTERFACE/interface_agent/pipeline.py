from .config import *
import json
import traceback
from pathlib import Path
from typing import List, Optional, Union

from PIL import Image

try:
    from tqdm.auto import tqdm
except Exception:
    def tqdm(iterable, *args, **kwargs):
        return iterable

from .analysis import analyze_screen_image, generate_ui_structure
from .docx_writer import create_ui_design_docx, save_integrated_ui_design_json
from .extractors import (
    collect_image_paths,
    collect_requirement_json_paths,
    ensure_docx_output_path,
    load_requirement_summary_json,
)


def run_ui_design_agent(
    requirement_json_paths: Optional[Union[str, Path, List[Union[str, Path]]]] = None,
    image_paths: Optional[Union[str, Path, List[Union[str, Path]]]] = None,
    output_docx_path: Path = OUTPUT_DOCX_PATH,
    max_images: Optional[int] = None,
):
    """사용자 요구사항 정의서 JSON과 프로토타입 이미지를 읽어 DOCX를 생성합니다."""
    output_docx_path = ensure_docx_output_path(output_docx_path)

    print("[1/5] 입력 파일 수집 및 사용자 요구사항 정의서 JSON 로드")
    requirement_json_file_paths = collect_requirement_json_paths(requirement_json_paths)
    image_file_paths = collect_image_paths(image_paths)
    if max_images is not None:
        if max_images < 1:
            raise ValueError("max_images는 1 이상이어야 합니다.")
        image_file_paths = image_file_paths[:max_images]
    print("사용자 요구사항 정의서 JSON 수:", len(requirement_json_file_paths), [p.name for p in requirement_json_file_paths])
    print("이미지 수:", len(image_file_paths), [p.name for p in image_file_paths])

    print("[2/5] 사용자 요구사항 정의서 JSON 확인")
    requirement_summary = load_requirement_summary_json(requirement_json_file_paths)
    print("요구사항 수:", len(requirement_summary.get("requirements", [])))
    (OUTPUT_DIR / "requirement_summary.json").write_text(
        json.dumps(requirement_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("[3/5] 프로토타입 이미지 파일 확인")
    for image_path in image_file_paths:
        try:
            with Image.open(image_path) as img:
                img.verify()
        except Exception as e:
            raise RuntimeError(f"이미지 파일을 열 수 없습니다: {image_path}") from e

    print("[4/5] 화면 이미지 분석 및 번호 버튼 이미지 생성")
    screen_specs = []
    for idx, image_path in enumerate(tqdm(image_file_paths), start=1):
        try:
            spec = analyze_screen_image(image_path, requirement_summary, idx)
            screen_specs.append(spec)
        except Exception:
            print("분석 실패:", image_path)
            traceback.print_exc()

    if not screen_specs:
        raise RuntimeError("분석된 화면이 없습니다.")

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

    (OUTPUT_DIR / "screen_specs.json").write_text(
        json.dumps(screen_specs, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("[5/5] 화면 구조도 생성 및 DOCX 저장")
    ui_structure = generate_ui_structure(screen_specs)
    (OUTPUT_DIR / "ui_structure.json").write_text(
        json.dumps(ui_structure, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    integrated_json_path = save_integrated_ui_design_json(
        requirement_summary=requirement_summary,
        ui_structure=ui_structure,
        screen_specs=screen_specs,
        output_docx_path=output_docx_path,
        output_json_path=OUTPUT_DIR / "ui_design_integrated.json",
    )
    print("통합 JSON 저장:", integrated_json_path.resolve())

    output_docx_path = create_ui_design_docx(
        requirement_summary=requirement_summary,
        ui_structure=ui_structure,
        screen_specs=screen_specs,
        output_path=output_docx_path,
    )

    if not Path(output_docx_path).exists():
        raise RuntimeError(f"DOCX 저장 실패: {output_docx_path}")

    print("완료:", output_docx_path.resolve())
    return output_docx_path, requirement_summary, ui_structure, screen_specs
