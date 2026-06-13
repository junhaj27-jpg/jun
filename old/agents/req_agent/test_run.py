import sys, os, json, logging, argparse

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(1, os.path.join(os.path.dirname(__file__), "..", "튜토리얼2"))
os.chdir(os.path.join(os.path.dirname(__file__), "..", "튜토리얼2"))

from app import run, modify

BASE       = os.path.join(os.path.dirname(__file__), "..", "튜토리얼2")
OUT_DIR    = os.path.join(os.path.dirname(__file__), "output")
FINAL_PATH = os.path.join(OUT_DIR, "final_reqs.json")


def load_rfp():
    path = os.path.join(BASE, "서민금융진흥원 AI기반 통합 플랫폼 구축 사업 제안요청서_final.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    rfp = data["requirements"] if isinstance(data, dict) and "requirements" in data else data
    print(f"✅ RFP {len(rfp)}개 로드")
    return rfp


def load_minutes(path=None):
    fpath = os.path.join(BASE, path) if path else os.path.join(BASE, "data", "RFP_변경_회의록.txt")
    with open(fpath, encoding="utf-8") as f:
        text = f.read()
    print(f"✅ 회의록 {len(text)}자 로드")
    return text


def load_existing():
    if not os.path.exists(FINAL_PATH):
        print("❌ output/final_reqs.json 없음 -- generate 먼저 실행하세요")
        sys.exit(1)
    with open(FINAL_PATH, encoding="utf-8") as f:
        reqs = json.load(f)
    print(f"✅ 기존 요구사항 {len(reqs)}개 로드")
    return reqs


def save(result):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(FINAL_PATH, "w", encoding="utf-8") as f:
        json.dump(result["final_reqs"], f, ensure_ascii=False, indent=2)
    print(f"✅ 저장: {FINAL_PATH}")
    if result["review_reqs"]:
        rpath = os.path.join(OUT_DIR, "review_reqs.json")
        with open(rpath, "w", encoding="utf-8") as f:
            json.dump(result["review_reqs"], f, ensure_ascii=False, indent=2)
        print(f"✅ 검토 목록: {rpath}")


def print_result(result):
    print("\n=== 최종 요구사항 ===")
    print(json.dumps(result["final_reqs"], ensure_ascii=False, indent=2))
    print(f"\n=== 검토 필요 ({len(result['review_reqs'])}건) ===")
    print(json.dumps(result["review_reqs"], ensure_ascii=False, indent=2) if result["review_reqs"] else "없음")


parser = argparse.ArgumentParser(description="AI-DLC 요구사항 생성/수정")
sub    = parser.add_subparsers(dest="command")
sub.add_parser("generate", help="Agent 1 -- RFP + 회의록으로 요구사항 생성")
sub.add_parser("sample",   help="샘플 JSON 1개로 docx 생성 테스트")
p_mod = sub.add_parser("modify", help="Agent 2 -- 기존 요구사항 수정")
group = p_mod.add_mutually_exclusive_group(required=True)
group.add_argument("--text", type=str)
group.add_argument("--file", type=str)

args = parser.parse_args()
if not args.command:
    parser.print_help()
    sys.exit(0)

if args.command == "sample":
    print("\n" + "="*50 + "\n샘플 docx 테스트\n" + "="*50)
    sample = [{
        "requirement_id":      "REQ-001",
        "requirement_name":    "AI 기반 상담 챗봇",
        "requirement_type":    "기능",
        "description":         "시스템은 AI 기반 챗봇을 통하여 24시간 금융 상담 서비스를 제공하여야 한다.",
        "source":              ["서민금융진흥원_제안요청서.docx", "FUR-001"],
        "constraints":         ["응답시간 3초 이내", "한국어 지원 필수"],
        "priority":            "상",
        "validation_criteria": ["챗봇 응답 정확도 90% 이상"],
        "note":                None,
        "status":              "신규",
    }]
    os.makedirs(OUT_DIR, exist_ok=True)
    from services.docx_service import generate_docx
    docx_path = generate_docx(sample, prefix="sample")
    print(f"✅ docx 저장: {docx_path}")
    with open(os.path.join(OUT_DIR,"sample_req.json"),"w",encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)
    sys.exit(0)

elif args.command == "generate":
    print("\n" + "="*50 + "\nAgent 1 -- 요구사항 생성\n" + "="*50)
    result = run(load_rfp(), load_minutes())

elif args.command == "modify":
    print("\n" + "="*50 + "\nAgent 2 -- 요구사항 수정\n" + "="*50)
    instruction = args.text if args.text else load_minutes(args.file)
    result = modify(load_existing(), instruction)

print_result(result)
save(result)

# python test_run.py generate
# python test_run.py sample
# python test_run.py modify --text "REQ-001 우선순위 변경"
# python test_run.py modify --file "data/RFP_변경_회의록.txt"
