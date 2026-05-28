from .config import *
from PIL import Image, ImageDraw, ImageFont

def clamp(value: float, min_value: float, max_value: float) -> float:
    """숫자 값이 지정한 최소/최대 범위를 벗어나지 않게 보정합니다."""
    return max(min_value, min(max_value, value))


def get_marker_font(size: int):
    """번호 버튼에 사용할 굵은 글꼴을 찾고, 없으면 기본 글꼴을 반환합니다."""
    font_candidates = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/malgunbd.ttf",
        "C:/Windows/Fonts/Arial.ttf",
    ]
    for font_path in font_candidates:
        if Path(font_path).exists():
            return ImageFont.truetype(font_path, size=size)
    return ImageFont.load_default()


def fallback_button_markers(process_contents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """모델이 좌표를 주지 않았을 때 화면 가장자리 기준의 기본 번호 버튼 좌표를 생성합니다."""
    fallback_positions = [
        (0.72, 0.08), (0.90, 0.15), (0.20, 0.18), (0.20, 0.38),
        (0.58, 0.38), (0.20, 0.78), (0.50, 0.78), (0.82, 0.78),
    ]
    markers = []
    for idx, item in enumerate(process_contents):
        x_ratio, y_ratio = fallback_positions[idx % len(fallback_positions)]
        markers.append({
            "no": item.get("no", idx + 1),
            "target_area": item.get("title", ""),
            "x_ratio": x_ratio,
            "y_ratio": y_ratio,
        })
    return markers


def normalize_button_markers(screen_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """처리내용 번호와 매칭되는 버튼 위치 목록을 정리하고 누락된 좌표를 보완합니다."""
    process_contents = screen_spec.get("process_contents", []) or []
    process_numbers = [int(item.get("no", idx + 1)) for idx, item in enumerate(process_contents)]
    raw_markers = screen_spec.get("button_markers", []) or []
    marker_by_no = {}

    for marker in raw_markers:
        try:
            no = int(marker.get("no"))
            marker_by_no[no] = marker
        except Exception:
            continue

    fallback_markers = fallback_button_markers(process_contents)
    fallback_by_no = {int(marker["no"]): marker for marker in fallback_markers}
    normalized = []

    for no in process_numbers:
        marker = marker_by_no.get(no, fallback_by_no.get(no, {"no": no, "x_ratio": 0.08, "y_ratio": 0.12}))
        normalized.append({
            "no": no,
            "target_area": marker.get("target_area", ""),
            "x_ratio": clamp(float(marker.get("x_ratio", 0.08)), 0.03, 0.97),
            "y_ratio": clamp(float(marker.get("y_ratio", 0.10)), 0.04, 0.96),
        })
    return normalized


def align_button_markers_to_process_contents(screen_spec: Dict[str, Any]) -> Dict[str, Any]:
    """처리내용 번호와 버튼 마커 번호가 1:1로 맞도록 화면 명세를 정리합니다."""
    screen_copy = dict(screen_spec)
    process_contents = screen_copy.get("process_contents", []) or []
    normalized_process = []
    for idx, item in enumerate(process_contents, start=1):
        if not isinstance(item, dict):
            continue
        item_copy = dict(item)
        item_copy["no"] = idx
        normalized_process.append(item_copy)
    screen_copy["process_contents"] = normalized_process
    screen_copy["button_markers"] = normalize_button_markers(screen_copy)
    return screen_copy


def draw_number_marker(draw: ImageDraw.ImageDraw, x: int, y: int, radius: int, no: int, font) -> None:
    """프로토타입 이미지 위에 파란 원형 번호 버튼을 그립니다."""
    shadow_offset = max(2, radius // 8)
    draw.ellipse(
        (x - radius + shadow_offset, y - radius + shadow_offset, x + radius + shadow_offset, y + radius + shadow_offset),
        fill=(20, 34, 60, 70),
    )
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(37, 99, 235, 255), outline=(255, 255, 255, 255), width=max(3, radius // 8))
    label = str(no)
    bbox = draw.textbbox((0, 0), label, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    draw.text((x - text_w / 2, y - text_h / 2 - radius * 0.04), label, fill=(255, 255, 255, 255), font=font)


def create_numbered_prototype_image(image_path: Path, screen_spec: Dict[str, Any], out_dir: Path) -> Path:
    """처리내용 번호 버튼을 원본 프로토타입 이미지에 합성해 새 이미지로 저장합니다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    image_path = Path(image_path)
    with Image.open(image_path).convert("RGBA") as image:
        width, height = image.size
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        radius = int(clamp(min(width, height) * 0.025, 18, 34))
        font = get_marker_font(int(radius * 1.15))

        for marker in normalize_button_markers(screen_spec):
            x = int(clamp(marker["x_ratio"], radius / width, 1 - radius / width) * width)
            y = int(clamp(marker["y_ratio"], radius / height, 1 - radius / height) * height)
            draw_number_marker(draw, x, y, radius, marker["no"], font)

        result = Image.alpha_composite(image, overlay).convert("RGB")
        output_path = out_dir / f"{image_path.stem}_numbered.png"
        result.save(output_path, quality=95)
        return output_path
