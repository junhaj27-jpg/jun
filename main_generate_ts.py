import argparse


def build_parser():
    parser = argparse.ArgumentParser(description="통합시험 시나리오 생성")
    parser.add_argument("--requirement-json-path", default="./data/requirements/requirement.json")
    parser.add_argument(
        "--ui",
        nargs="*",
        default=[],
        help="UI 설계서 JSON 파일 경로 목록",
    )
    parser.add_argument("--output-json-path", default="./json_temp/ts_agent_output.json")
    parser.add_argument("--output-docx-path", default="./output/integration_test_scenario.docx")
    parser.add_argument("--max-retries", type=int, default=1)
    return parser


def main():
    args = build_parser().parse_args()

    from workflows.ts_workflow import compile_ts_graph

    app = compile_ts_graph()
    result = app.invoke(
        {
            "requirement_json_path": args.requirement_json_path,
            "ui_paths": args.ui,
            "output_json_path": args.output_json_path,
            "output_docx_path": args.output_docx_path,
            "max_retries": args.max_retries,
        }
    )

    if result.get("status") != "VALID":
        raise RuntimeError("통합시험 시나리오 생성 실패")

    print("[완료] 통합시험 시나리오 JSON:", result.get("output_json_path"))
    print("[완료] 통합시험 시나리오 DOCX:", result.get("output_docx_path"))
    print("[요약]", result.get("summary", {}))


if __name__ == "__main__":
    main()
