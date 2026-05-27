# req_agent/test_run.py
import sys, os, json, logging, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(1, os.path.join(os.path.dirname(__file__), "..", "data_pipeline"))
os.chdir(os.path.join(os.path.dirname(__file__), "..", "data_pipeline"))

# logging.basicConfig(level=logging.INFO)

from app import run, modify

BASE       = os.path.join(os.path.dirname(__file__), "..", "data_pipeline")
OUT_DIR    = os.path.join(os.path.dirname(__file__), "output")
FINAL_PATH = os.path.join(OUT_DIR, "final_reqs.json")


def load_rfp() -> list[dict]:
    path = os.path.join(BASE, "서민금융진흥원 AI기반 통합 플랫폼 구축 사업 제안요청서_final.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    rfp = data["requirements"] if isinstance(data, dict) and "requirements" in data else data
    print(f" RFP {len(rfp)}개 로드")
    return rfp


def load_minutes(path: str = None) -> str:
    fpath = os.path.join(BASE, path) if path else os.path.join(BASE, "data", "RFP_변경_회의록.txt")
    with open(fpath, encoding="utf-8") as f:
        text = f.read()
    print(f" 회의록 {len(text)}자 로드: {fpath}")
    return text


def load_existing() -> list[dict]:
    if not os.path.exists(FINAL_PATH):
        print(" output/final_reqs.json 없음 — generate 먼저 실행하세요")
        sys.exit(1)
    with open(FINAL_PATH, encoding="utf-8") as f:
        reqs = json.load(f)
    print(f" 기존 요구사항 {len(reqs)}개 로드")
    return reqs


def save(result: dict):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(FINAL_PATH, "w", encoding="utf-8") as f:
        json.dump(result["final_reqs"], f, ensure_ascii=False, indent=2)
    print(f" 저장: {FINAL_PATH}")

    if result["review_reqs"]:
        rpath = os.path.join(OUT_DIR, "review_reqs.json")
        with open(rpath, "w", encoding="utf-8") as f:
            json.dump(result["review_reqs"], f, ensure_ascii=False, indent=2)
        print(f" 검토 목록: {rpath}")


def print_result(result: dict):
    print("\n=== 최종 요구사항 ===")
    print(json.dumps(result["final_reqs"], ensure_ascii=False, indent=2))
    print(f"\n=== 검토 필요 ({len(result['review_reqs'])}건) ===")
    print(json.dumps(result["review_reqs"], ensure_ascii=False, indent=2) if result["review_reqs"] else "없음")


# ── CLI ──────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="AI-DLC 요구사항 생성/수정")
sub    = parser.add_subparsers(dest="command")

# generate
sub.add_parser("generate", help="Agent 1 — RFP + 회의록으로 요구사항 생성")

# sample
sub.add_parser("sample", help="샘플 JSON 1개로 docx 생성 테스트")

# modify
p_mod = sub.add_parser("modify", help="Agent 2 — 기존 요구사항 수정")
group = p_mod.add_mutually_exclusive_group(required=True)
group.add_argument("--text", type=str,  help="수정 지시 텍스트 직접 입력")
group.add_argument("--file", type=str,  help="수정 회의록 파일 경로 (data/ 기준)")

args = parser.parse_args()

if not args.command:
    parser.print_help()
    sys.exit(0)

# ── 실행 ─────────────────────────────────────────────────
if args.command == "sample":
    print("\n" + "="*50)
    print("샘플 docx 생성 테스트")
    print("="*50)

    sample = [
        {
            "requirement_id":      "REQ-001",
            "requirement_name":    "AI 기반 상담 챗봇",
            "requirement_type":    "기능",
            "description":         "시스템은 AI 기반 챗봇을 통하여 24시간 금융 상담 서비스를 제공하여야 한다.",
            "source":              ["서민금융진흥원_제안요청서.docx"],
            "constraints":         ["응답시간 3초 이내", "한국어 지원 필수"],
            "priority":            "상",
            "validation_criteria": ["챗봇 응답 정확도 90% 이상", "동시 접속 100명 처리"],
            "note":                None,
        }
    ]

    os.makedirs(OUT_DIR, exist_ok=True)

    from services.docx_service import generate_docx
    docx_path = generate_docx(sample, prefix="sample")
    print(f"✅ docx 저장: {docx_path}")

    json_path = os.path.join(OUT_DIR, "sample_req.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)
    print(f"✅ JSON 저장: {json_path}")

    sys.exit(0)

elif args.command == "generate":
    print("\n" + "="*50)
    print("Agent 1 — 요구사항 생성")
    print("="*50)
    result = run(load_rfp(), load_minutes())

elif args.command == "modify":
    print("\n" + "="*50)
    print("Agent 2 — 요구사항 수정")
    print("="*50)
    instruction = args.text if args.text else load_minutes(args.file)
    result = modify(load_existing(), instruction)

print_result(result)
save(result)


# 최종 Docx 자동으로 만들기 위해 선행적으로 필요함
# # req_agent 폴더로 이동
# cd C:\skn24\수업자료\08_large_language_model\00.final_project\req_agent

# # npm 초기화 (package.json 없으면)
# npm init -y

# # docx 설치
# npm install docx

# =================== 실행 코드 ================

# # 최초 생성
# python test_run.py generate

# # 샘플 docx 테스트
# python test_run.py sample

# # 텍스트로 수정
# python test_run.py modify --text "REQ-001 우선순위 상으로 변경, REQ-003 삭제"

# # 새 회의록 파일로 수정
# python test_run.py modify --file "data/RFP_변경_회의록.txt"

# # 도움말
# python test_run.py --help

