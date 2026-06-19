from __future__ import annotations

import argparse
import json
from pathlib import Path

from requirements_gold_agent import RequirementsGenerationService


def _summary(result: dict, source_file: str | None = None) -> dict:
    item = {
        "document_id": result.get("document_id"),
        "gold_requirement_count": result.get("gold_requirement_count"),
        "output_file": result.get("output_file"),
        "quality_status": (result.get("quality") or {}).get("status"),
        "fallback_count": (result.get("quality") or {}).get("fallback_count"),
    }
    if source_file:
        item = {"source_file": source_file, **item}
    return item


def main() -> None:
    parser = argparse.ArgumentParser(description="RFP 기능 요구사항 JSON을 GOLD 요구사항명세서로 생성합니다.")
    parser.add_argument("--input", required=True, help="입력 JSON 파일 또는 입력 폴더")
    parser.add_argument("--output-dir", default="./outputs", help="결과 저장 폴더")
    parser.add_argument("--glob", default="*_기능전체_입력.json", help="입력이 폴더일 때 처리할 파일 패턴")
    parser.add_argument("--job-id", default=None, help="단일 파일 실행 시 결과 폴더명. 미지정 시 document_id 사용")
    parser.add_argument("--resume", action="store_true", help="기존 결과 폴더를 삭제하지 않고 이어서 실행")
    parser.add_argument("--no-warmup", action="store_true", help="실행 전 warmup 생략. 일반적으로 사용하지 않음")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    service = RequirementsGenerationService.get_instance()
    if not args.no_warmup:
        service.warmup()

    replace_existing = not args.resume

    if input_path.is_file():
        result = service.generate_from_file(input_path, output_dir=output_dir, job_id=args.job_id, replace_existing=replace_existing)
        summary = _summary(result, input_path.name)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if not input_path.is_dir():
        raise FileNotFoundError(f"입력 경로가 파일 또는 폴더가 아닙니다: {input_path}")

    files = sorted(input_path.glob(args.glob))
    if not files:
        raise FileNotFoundError(f"처리할 입력 파일이 없습니다: {input_path / args.glob}")

    summaries = []
    for path in files:
        print(f"\n[RUN] {path}", flush=True)
        result = service.generate_from_file(path, output_dir=output_dir, replace_existing=replace_existing)
        summaries.append(_summary(result, path.name))

    summary_path = output_dir / "run_summary.json"
    summary_path.write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary_file": str(summary_path), "documents": summaries}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
