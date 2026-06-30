from __future__ import annotations

import argparse
import json
from pathlib import Path

from .service import RequirementsGenerationService


def main() -> None:
    parser = argparse.ArgumentParser(description="기능전체 입력을 최종 GOLD 요구사항으로 생성")
    parser.add_argument("--input", required=True, help="입력 JSON 파일 또는 폴더")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--glob", default="*_기능전체_입력.json")
    parser.add_argument("--job-id", default=None, help="단일 파일 실행 폴더명")
    args = parser.parse_args()
    service = RequirementsGenerationService.get_instance()
    service.warmup()
    target = Path(args.input)
    if target.is_file():
        result = service.generate_from_file(target, output_dir=args.output_dir, job_id=args.job_id)
        print(json.dumps({"document_id": result["document_id"], "gold_requirement_count": result["gold_requirement_count"], "quality": result["quality"]}, ensure_ascii=False, indent=2))
        return
    if not target.is_dir():
        raise FileNotFoundError(target)
    files = sorted(target.glob(args.glob))
    if not files:
        raise FileNotFoundError(f"입력 파일 없음: {target / args.glob}")
    summaries = []
    for path in files:
        result = service.generate_from_file(path, output_dir=args.output_dir)
        summaries.append({"file": path.name, "document_id": result["document_id"], "gold_requirement_count": result["gold_requirement_count"], "quality_status": result["quality"]["status"]})
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
