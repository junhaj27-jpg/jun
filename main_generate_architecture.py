import argparse


def build_parser():
    parser = argparse.ArgumentParser(description="아키텍처 설계서 생성")
    parser.add_argument("--requirement-json-path", default=None)
    parser.add_argument("--infra-spec-path", default=None)
    parser.add_argument("--output-json-path", default="./json_temp/architecture_agent_output.json")
    parser.add_argument("--output-md-path", default="./output/architecture_report.md")
    parser.add_argument("--output-docx-path", default="./output/architecture_report.docx")
    parser.add_argument("--output-image-path", default="./output/architecture_diagram.png")
    parser.add_argument(
        "--no-image",
        action="store_true",
        help="Mermaid PNG 렌더링을 건너뜁니다.",
    )
    return parser


def main():
    args = build_parser().parse_args()

    from workflows.architecture_workflow import compile_architecture_graph

    app = compile_architecture_graph()
    initial_state = {
        "render_image": not args.no_image,
        "output_json_path": args.output_json_path,
        "output_md_path": args.output_md_path,
        "output_docx_path": args.output_docx_path,
        "output_image_path": args.output_image_path,
    }
    if args.requirement_json_path:
        initial_state["requirement_json_path"] = args.requirement_json_path
    if args.infra_spec_path:
        initial_state["infra_spec_path"] = args.infra_spec_path

    result = app.invoke(initial_state)

    if result.get("status") != "VALID":
        raise RuntimeError(f"아키텍처 설계서 생성 실패: {result.get('validation_result')}")

    print("[완료] 아키텍처 JSON:", result.get("output_json_path"))
    print("[완료] 아키텍처 Markdown:", result.get("output_md_path"))
    print("[완료] 아키텍처 DOCX:", result.get("output_docx_path"))
    if result.get("output_image_path"):
        print("[완료] 아키텍처 이미지:", result.get("output_image_path"))


if __name__ == "__main__":
    main()
