import argparse


def build_parser():
    parser = argparse.ArgumentParser(description="사용자 인터페이스 설계서 생성")
    parser.add_argument("--requirement-path", default=None)
    parser.add_argument("--image-path", default=None)
    parser.add_argument("--output-json-path", default="./json_temp/interface/ui_design_integrated.json")
    parser.add_argument("--output-docx-path", default="./output/interface/사용자 인터페이스 설계서.docx")
    parser.add_argument("--work-dir", default="./json_temp/interface")
    parser.add_argument("--max-images", type=int, default=1)
    parser.add_argument(
        "--all-images",
        action="store_true",
        help="입력 폴더의 모든 프로토타입 이미지를 처리합니다.",
    )
    return parser


def main():
    args = build_parser().parse_args()

    from agents.interface_agent.config import PROTOTYPE_DIR, REQUIREMENT_DIR
    from workflows.interface_workflow import compile_interface_graph

    result = compile_interface_graph().invoke(
        {
            "requirement_paths": args.requirement_path or str(REQUIREMENT_DIR),
            "image_paths": args.image_path or str(PROTOTYPE_DIR),
            "output_json_path": args.output_json_path,
            "output_docx_path": args.output_docx_path,
            "work_dir": args.work_dir,
            "max_images": None if args.all_images else args.max_images,
        }
    )

    if result.get("status") != "VALID":
        raise RuntimeError("사용자 인터페이스 설계서 생성 실패")

    print("[완료] 사용자 인터페이스 설계서 통합 JSON:", result.get("output_json_path"))
    print("[완료] 사용자 인터페이스 설계서 DOCX:", result.get("output_docx_path"))
    print("[요약] 화면 수:", len(result.get("screen_specs", [])))


if __name__ == "__main__":
    main()
