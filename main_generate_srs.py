import argparse
import json
import os
from pathlib import Path


DEFAULT_RFP_JSON_PATH = (
    "./data/requirement_sources/"
    "서민금융진흥원 AI기반 통합 플랫폼 구축 사업 제안요청서_final.json"
)
DEFAULT_MINUTES_PATH = "./data/requirement_sources/meeting_minutes/RFP_변경_회의록.txt"
DEFAULT_OUTPUT_JSON_PATH = "./json_temp/srs_agent_output.json"
DEFAULT_EXISTING_REQS_PATH = "./json_temp/srs_agent_output.json"


def _load_rfp(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and isinstance(data.get("requirements"), list):
        return data["requirements"]
    if isinstance(data, list):
        return data
    raise ValueError(f"RFP JSON 형식을 확인하세요: {path}")


def _load_text(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _load_requirements(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and isinstance(data.get("final_reqs"), list):
        return data["final_reqs"]
    if isinstance(data, dict) and isinstance(data.get("requirements"), list):
        return data["requirements"]
    if isinstance(data, list):
        return data
    raise ValueError(f"기존 요구사항 JSON 형식을 확인하세요: {path}")


def _save_result(result: dict, output_json_path: str):
    Path(output_json_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


def _save_final_reqs(result: dict, output_reqs_path: str | None):
    if not output_reqs_path:
        return
    Path(output_reqs_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_reqs_path, "w", encoding="utf-8") as f:
        json.dump(result.get("final_reqs", []), f, ensure_ascii=False, indent=2)


def generate_mode(args):
    from agents.srs_app import run

    rfp_json_path = args.rfp_json_path or os.getenv("SRS_RFP_JSON_PATH", DEFAULT_RFP_JSON_PATH)
    minutes_path = args.minutes_path or os.getenv("SRS_MINUTES_PATH", DEFAULT_MINUTES_PATH)
    output_json_path = args.output_json_path or os.getenv("SRS_OUTPUT_JSON_PATH", DEFAULT_OUTPUT_JSON_PATH)

    if not Path(rfp_json_path).exists():
        raise FileNotFoundError(f"SRS RFP JSON을 찾지 못했습니다: {rfp_json_path}")
    if not Path(minutes_path).exists():
        raise FileNotFoundError(
            "SRS 회의록 파일을 찾지 못했습니다. "
            f"SRS_MINUTES_PATH를 지정하거나 기본 위치에 파일을 두세요: {minutes_path}"
        )

    result = run(
        rfp=_load_rfp(rfp_json_path),
        minutes=_load_text(minutes_path),
        save_docx=args.save_docx,
    )

    _save_result(result, output_json_path)
    _save_final_reqs(result, args.output_reqs_path)

    if result.get("review_reqs"):
        print(f"[검토 필요] {len(result['review_reqs'])}건")

    print("[완료] SRS JSON:", output_json_path)
    if args.output_reqs_path:
        print("[완료] SRS final_reqs:", args.output_reqs_path)
    if args.save_docx:
        print("[완료] SRS DOCX: output/generated_*.docx")


def modify_mode(args):
    from agents.srs_app import modify

    existing_reqs_path = args.existing_reqs_path or os.getenv(
        "SRS_EXISTING_REQS_PATH",
        DEFAULT_EXISTING_REQS_PATH,
    )
    output_json_path = args.output_json_path or os.getenv(
        "SRS_OUTPUT_JSON_PATH",
        DEFAULT_OUTPUT_JSON_PATH,
    )

    if not Path(existing_reqs_path).exists():
        raise FileNotFoundError(f"기존 SRS 요구사항 JSON을 찾지 못했습니다: {existing_reqs_path}")

    if args.instruction:
        instruction = args.instruction
    elif args.instruction_file:
        instruction = _load_text(args.instruction_file)
    else:
        raise ValueError("--instruction 또는 --instruction-file 중 하나가 필요합니다.")

    result = modify(
        existing_reqs=_load_requirements(existing_reqs_path),
        instruction=instruction,
        save_docx=args.save_docx,
    )

    _save_result(result, output_json_path)
    _save_final_reqs(result, args.output_reqs_path)

    if result.get("review_reqs"):
        print(f"[검토 필요] {len(result['review_reqs'])}건")

    print("[완료] SRS 수정 JSON:", output_json_path)
    if args.output_reqs_path:
        print("[완료] SRS final_reqs:", args.output_reqs_path)
    if args.save_docx:
        print("[완료] SRS DOCX: output/modified_*.docx")


def build_parser():
    parser = argparse.ArgumentParser(description="SRS 요구사항 생성/수정 LangGraph 실행")
    parser.add_argument(
        "--no-docx",
        action="store_true",
        help="DOCX 생성을 건너뜁니다.",
    )

    sub = parser.add_subparsers(dest="command")

    generate = sub.add_parser("generate", help="RFP JSON + 회의록으로 SRS 신규 생성")
    generate.add_argument("--rfp-json-path", default=None)
    generate.add_argument("--minutes-path", default=None)
    generate.add_argument("--output-json-path", default=None)
    generate.add_argument("--output-reqs-path", default="./json_temp/srs_final_reqs.json")

    modify_parser = sub.add_parser("modify", help="기존 SRS 요구사항을 수정 지시로 변경")
    modify_parser.add_argument("--existing-reqs-path", default=None)
    modify_parser.add_argument("--instruction", default=None)
    modify_parser.add_argument("--instruction-file", default=None)
    modify_parser.add_argument("--output-json-path", default=None)
    modify_parser.add_argument("--output-reqs-path", default="./json_temp/srs_final_reqs.json")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.command = args.command or "generate"
    args.save_docx = not args.no_docx

    if args.command == "generate":
        generate_mode(args)
    elif args.command == "modify":
        modify_mode(args)
    else:
        parser.print_help()
        raise SystemExit(2)


if __name__ == "__main__":
    main()
