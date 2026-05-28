from agents.interface_agent.config import *

def split_path_input(path_input: Optional[Union[str, Path, List[Union[str, Path]]]]) -> List[Path]:
    """문자열/Path/리스트 입력을 여러 개의 Path 목록으로 변환합니다."""
    if path_input is None:
        return []
    if isinstance(path_input, (str, Path)):
        raw_items = re.split(r"[,;\n]+", str(path_input))
    else:
        raw_items = [str(item) for item in path_input]
    return [Path(item.strip().strip('"').strip("'")) for item in raw_items if item and item.strip()]


def prompt_paths(label: str, default_dir: Path, allowed_exts: set) -> List[Path]:
    """실행 시 사용자에게 파일 또는 폴더 경로를 입력받습니다."""
    ext_text = ", ".join(sorted(allowed_exts))
    user_input = input(f"{label} 파일/폴더 경로를 입력하세요({ext_text}, 여러 개는 쉼표로 구분, 기본: {default_dir}): ").strip()
    return split_path_input(user_input or default_dir)


def collect_files(path_input: Optional[Union[str, Path, List[Union[str, Path]]]], allowed_exts: set, label: str) -> List[Path]:
    """입력받은 파일/폴더 경로에서 허용 확장자 파일을 재귀적으로 수집합니다."""
    paths = split_path_input(path_input)
    files = []

    for path in paths:
        if path.is_dir():
            files.extend(sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in allowed_exts))
        elif path.is_file():
            if path.suffix.lower() not in allowed_exts:
                raise ValueError(f"지원하지 않는 {label} 파일 형식입니다: {path.name}. 허용 형식: {sorted(allowed_exts)}")
            files.append(path)
        else:
            raise FileNotFoundError(f"{label} 경로를 찾을 수 없습니다: {path}")

    unique_files = []
    seen = set()
    for file_path in files:
        resolved = file_path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique_files.append(file_path)

    if not unique_files:
        raise RuntimeError(f"{label} 파일을 찾지 못했습니다. 허용 형식: {sorted(allowed_exts)}")

    return unique_files


def collect_requirement_json_paths(path_input: Optional[Union[str, Path, List[Union[str, Path]]]] = None) -> List[Path]:
    """사용자 요구사항 정의서 JSON 파일을 한 개 이상 수집합니다."""
    if path_input is None:
        path_input = prompt_paths("사용자 요구사항 정의서 JSON", INPUT_DIR, SUPPORTED_REQUIREMENT_JSON_EXTS)
    return collect_files(path_input, SUPPORTED_REQUIREMENT_JSON_EXTS, "사용자 요구사항 정의서 JSON")


def collect_image_paths(path_input: Optional[Union[str, Path, List[Union[str, Path]]]] = None) -> List[Path]:
    """프로토타입 이미지 파일(png, jpg, jpeg)을 한 개 이상 수집합니다."""
    if path_input is None:
        path_input = prompt_paths("프로토타입 이미지", INPUT_DIR, SUPPORTED_IMAGE_EXTS)
    return collect_files(path_input, SUPPORTED_IMAGE_EXTS, "프로토타입 이미지")



def load_requirement_summary_json(json_paths: List[Path]) -> Dict[str, Any]:
    """앞 단계 Agent가 생성한 사용자 요구사항 정의서 JSON을 읽어 화면 분석 입력으로 사용합니다."""
    loaded_items = []
    for json_path in json_paths:
        with open(json_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        if isinstance(data, list):
            loaded_items.extend(data)
        elif isinstance(data, dict):
            loaded_items.append(data)
        else:
            raise ValueError(f"JSON 최상위 구조는 객체 또는 배열이어야 합니다: {json_path}")

    if len(loaded_items) == 1 and isinstance(loaded_items[0], dict):
        summary = loaded_items[0]
    else:
        requirements = []
        for item in loaded_items:
            if isinstance(item, dict) and isinstance(item.get("requirements"), list):
                requirements.extend(item["requirements"])
            elif isinstance(item, dict):
                requirements.append(item)
        summary = {"requirements": requirements, "requirements_count": len(requirements)}

    if "requirements" not in summary or not isinstance(summary.get("requirements"), list):
        raise ValueError("사용자 요구사항 정의서 JSON에는 requirements 배열이 필요합니다.")

    summary.setdefault("requirements_count", len(summary.get("requirements", [])))
    summary.setdefault("system_name", summary.get("project_name", ""))
    summary.setdefault("subsystem_name", "")
    return summary


def ensure_docx_output_path(output_path: Path) -> Path:
    """출력 파일 확장자를 docx로 제한하고 저장 폴더를 준비합니다."""
    output_path = Path(output_path)
    if output_path.suffix.lower() != ".docx":
        output_path = output_path.with_suffix(".docx")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path
