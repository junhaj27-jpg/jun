"""인터페이스 화면 이미지에 처리내용 번호 배지를 합성합니다."""

from pathlib import Path
import re
from typing import Any


FALLBACK_POSITIONS = [
    (0.72, 0.08),
    (0.90, 0.15),
    (0.20, 0.18),
    (0.20, 0.38),
    (0.58, 0.38),
    (0.20, 0.78),
    (0.50, 0.78),
    (0.82, 0.78),
]
TARGET_DOC_IMAGE_WIDTH_PX = 1800


def enrich_interface_screens(
    screens: list[dict[str, Any]],
    *,
    output_dir: str | Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """화면 상세 설계 필드와 번호 배지 이미지를 생성합니다."""

    warnings: list[dict[str, Any]] = []
    enriched = []
    for index, screen in enumerate(screens, start=1):
        item = ensure_screen_design_fields(screen, index)
        image_path = str(item.get("image_path") or "")
        if image_path and item.get("match_status") in {"MATCHED", "UNMAPPED_IMAGE", "IMAGE_MODIFY_REQUIRED", "IMAGE_DELETE_CANDIDATE"}:
            try:
                item["annotated_image_path"] = str(
                    create_numbered_prototype_image(Path(image_path), item, Path(output_dir))
                )
            except Exception as exc:
                warnings.append(
                    {
                        "code": "INTERFACE_IMAGE_MARKER_FAILED",
                        "message": str(exc),
                        "image_path": image_path,
                    }
                )
        enriched.append(item)
    return enriched, warnings


def ensure_screen_design_fields(screen: dict[str, Any], index: int) -> dict[str, Any]:
    """DOCX 화면 상세 설계에 필요한 필드를 보강합니다."""

    item = dict(screen)
    analysis = item.get("analysis") if isinstance(item.get("analysis"), dict) else {}
    item.setdefault("screen_id", f"SCR-{index:03d}")
    item.setdefault("screen_name", analysis.get("screen_name_candidate") or f"화면 {index}")
    item.setdefault("screen_type", analysis.get("screen_type") or "업무 화면")
    item.setdefault("menu_path", item.get("screen_name", ""))
    item.setdefault("screen_overview", item.get("description") or analysis.get("purpose") or "")

    process_contents = _normalize_process_contents(item.get("process_contents"), item, analysis)
    item["process_contents"] = process_contents
    item["button_markers"] = _normalize_button_markers(item.get("button_markers"), process_contents, analysis)
    return item


def build_ui_structure(screens: list[dict[str, Any]]) -> list[dict[str, str]]:
    """화면 목록을 Level1~Level4 구조도 행으로 변환합니다."""

    rows = []
    for screen in screens:
        menu_path = str(screen.get("menu_path") or screen.get("screen_name") or "")
        parts = [part.strip() for part in menu_path.replace("/", ">").split(">") if part.strip()]
        screen_type = str(screen.get("screen_type") or "업무 화면")
        screen_name = str(screen.get("screen_name") or screen.get("screen_id") or "")
        if len(parts) <= 1 and (not parts or parts[0] == screen_name):
            module_name, detail_name = _screen_menu_levels(screen_name)
            parts = ["AI 통합 플랫폼", module_name, screen_type, detail_name]
        rows.append(
            {
                "level1": parts[0] if len(parts) > 0 else screen_type,
                "level2": parts[1] if len(parts) > 1 else "",
                "level3": parts[2] if len(parts) > 2 else "",
                "level4": parts[3] if len(parts) > 3 else "",
            }
        )
    return rows


def create_numbered_prototype_image(image_path: Path, screen_spec: dict[str, Any], out_dir: Path) -> Path:
    """처리내용 번호 버튼을 원본 프로토타입 이미지에 합성해 새 이미지로 저장합니다."""

    from PIL import Image, ImageDraw, ImageFont

    out_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path).convert("RGBA") as image:
        image = _upscale_for_docx(image)
        width, height = image.size
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        radius = int(_clamp(min(width, height) * 0.022, 18, 32))
        font = _get_marker_font(ImageFont, int(radius * 1.25))

        markers = _normalize_button_markers(
            screen_spec.get("button_markers"),
            screen_spec.get("process_contents") or [],
            screen_spec.get("analysis") if isinstance(screen_spec.get("analysis"), dict) else {},
        )
        placed_rects: list[tuple[int, int, int, int]] = []
        for marker in markers:
            x, y = _resolve_marker_position(marker, width, height, radius, placed_rects)
            _draw_number_marker(draw, x, y, radius, int(marker["no"]), font)
            placed_rects.append((x - radius, y - radius, x + radius, y + radius))

        output_path = out_dir / f"{image_path.stem}_numbered.png"
        Image.alpha_composite(image, overlay).convert("RGB").save(output_path, optimize=True)
        return output_path


def _upscale_for_docx(image: Any) -> Any:
    from PIL import Image

    width, height = image.size
    if width >= TARGET_DOC_IMAGE_WIDTH_PX:
        return image
    scale = TARGET_DOC_IMAGE_WIDTH_PX / max(1, width)
    next_size = (TARGET_DOC_IMAGE_WIDTH_PX, max(1, int(height * scale)))
    resampling = getattr(getattr(Image, "Resampling", None), "LANCZOS", Image.LANCZOS)
    return image.resize(next_size, resampling)


def _normalize_process_contents(
    raw_process: Any,
    screen: dict[str, Any],
    analysis: dict[str, Any],
) -> list[dict[str, Any]]:
    areas = _candidate_areas(analysis)
    if isinstance(raw_process, list) and raw_process:
        process_contents = [
            {
                "no": index,
                "title": str(item.get("title") or item.get("name") or f"처리 {index}"),
                "description": str(item.get("description") or item.get("content") or ""),
                "requirement_basis": str(item.get("requirement_basis") or item.get("basis") or _basis(screen)),
                "component_id": str(item.get("component_id") or item.get("candidate_id") or ""),
                "component_bbox": item.get("component_bbox") if isinstance(item.get("component_bbox"), dict) else {},
            }
            for index, item in enumerate(raw_process, start=1)
            if isinstance(item, dict)
        ]
        return _renumber_process_contents(process_contents)

    process_contents = []
    for index, area in enumerate(areas, start=1):
        title = str(area.get("name") or area.get("title") or f"기능 영역 {index}")
        role = str(area.get("area_role") or area.get("description") or "")
        visible_texts = [str(value) for value in area.get("visible_texts", []) if value] if isinstance(area.get("visible_texts"), list) else []
        detail = role or f"{title} 영역에서 사용자가 필요한 정보를 확인하거나 업무를 처리합니다."
        if visible_texts:
            detail += " 표시 텍스트: " + ", ".join(visible_texts[:5])
        process_contents.append(
            {
                "no": index,
                "title": title,
                "description": detail,
                "requirement_basis": _basis(screen),
                "component_id": str(area.get("candidate_id") or area.get("component_id") or ""),
                "component_bbox": area.get("bbox") if isinstance(area.get("bbox"), dict) else {},
            }
        )
    if not process_contents:
        fallback_description = str(
            analysis.get("purpose")
            or screen.get("screen_overview")
            or screen.get("description")
            or ""
        ).strip()
        if fallback_description:
            process_contents.append(
                {
                    "no": 1,
                    "title": str(screen.get("screen_name") or analysis.get("screen_name_candidate") or "화면 처리"),
                    "description": fallback_description,
                    "requirement_basis": _basis(screen),
                }
            )
    return _renumber_process_contents(process_contents)


def _normalize_button_markers(
    raw_markers: Any,
    process_contents: list[dict[str, Any]],
    analysis: dict[str, Any],
) -> list[dict[str, Any]]:
    marker_by_no = {}
    if isinstance(raw_markers, list):
        for marker in raw_markers:
            if not isinstance(marker, dict):
                continue
            try:
                no = int(marker.get("no"))
            except Exception:
                continue
            marker_by_no[no] = marker

    areas = _candidate_areas(analysis)
    normalized = []
    for index, process in enumerate(process_contents, start=1):
        marker = marker_by_no.get(index)
        area = areas[index - 1] if index - 1 < len(areas) else {}
        fallback_x, fallback_y = FALLBACK_POSITIONS[(index - 1) % len(FALLBACK_POSITIONS)]
        process_bbox = process.get("component_bbox") if isinstance(process.get("component_bbox"), dict) else {}
        area_bbox = area.get("bbox") if isinstance(area.get("bbox"), dict) else {}
        bbox = process_bbox or area_bbox
        normalized.append(
            {
                "no": index,
                "target_area": str(
                    (marker or {}).get("target_area")
                    or area.get("name")
                    or process.get("title")
                    or f"기능 영역 {index}"
                ),
                "x_ratio": _ratio(_bbox_marker_x(bbox, (marker or {}).get("x_ratio", area.get("x_ratio", fallback_x))), fallback_x),
                "y_ratio": _ratio(_bbox_marker_y(bbox, (marker or {}).get("y_ratio", area.get("y_ratio", fallback_y))), fallback_y),
                "target_bbox": bbox,
            }
        )
    return normalized


def _functional_areas(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    components = analysis.get("component_candidates")
    if isinstance(components, list) and components:
        return [
            {
                "name": str(item.get("component_name") or item.get("name") or f"컴포넌트 {index}"),
                "visible_texts": item.get("texts") if isinstance(item.get("texts"), list) else [],
                "area_role": str(item.get("reason") or ""),
                "component_type": str(item.get("component_type") or "unknown"),
                "bbox": item.get("bbox") if isinstance(item.get("bbox"), dict) else {},
                "x_ratio": item.get("x_ratio"),
                "y_ratio": item.get("y_ratio"),
            }
            for index, item in enumerate(components, start=1)
            if isinstance(item, dict) and _is_marker_candidate(item)
        ]
    value = analysis.get("functional_areas")
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    value = analysis.get("content_areas")
    if isinstance(value, list):
        return [
            item if isinstance(item, dict) else {"name": str(item)}
            for item in value
        ]
    return []


def _candidate_areas(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    """VLM이 인식한 기능 영역 수만큼 배지 후보를 만듭니다."""

    functional_areas = _functional_areas(analysis)
    candidates = functional_areas if functional_areas else _fallback_areas(analysis)
    deduped = []
    seen: set[str] = set()
    for index, area in enumerate(candidates, start=1):
        name = str(area.get("name") or area.get("title") or f"기능 영역 {index}").strip()
        if not name or name in seen or not _is_marker_candidate({**area, "name": name}):
            continue
        seen.add(name)
        deduped.append({**area, "name": name})
    return deduped


def _fallback_areas(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    names = []
    for key in ("input_fields", "buttons", "user_actions", "navigation_candidates"):
        value = analysis.get(key)
        if isinstance(value, list):
            names.extend(str(item) for item in value if item)
    content_areas = analysis.get("content_areas")
    if isinstance(content_areas, list):
        for item in content_areas:
            if isinstance(item, dict):
                names.append(str(item.get("name") or item.get("title") or ""))
            elif item:
                names.append(str(item))
    if not names:
        return []
    return [
        {
            "name": name,
            "area_role": f"{name} 관련 화면 기능을 처리합니다.",
            "x_ratio": FALLBACK_POSITIONS[index % len(FALLBACK_POSITIONS)][0],
            "y_ratio": FALLBACK_POSITIONS[index % len(FALLBACK_POSITIONS)][1],
        }
        for index, name in enumerate(names)
        if name
    ]


def _renumber_process_contents(process_contents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {**item, "no": index}
        for index, item in enumerate(process_contents, start=1)
    ]


def _basis(screen: dict[str, Any]) -> str:
    ids = screen.get("matched_requirement_ids")
    if isinstance(ids, list) and ids:
        return ", ".join(str(value) for value in ids)
    return ""


def _ratio(value: Any, default: float) -> float:
    try:
        return _clamp(float(value), 0.03, 0.97)
    except Exception:
        return default


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _get_marker_font(image_font: Any, size: int) -> Any:
    for font_path in (
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/malgunbd.ttf",
        "C:/Windows/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    ):
        if Path(font_path).exists():
            return image_font.truetype(font_path, size=size)
    return image_font.load_default()


def _draw_number_marker(draw: Any, x: int, y: int, radius: int, no: int, font: Any) -> None:
    shadow_offset = max(2, radius // 8)
    draw.ellipse(
        (
            x - radius + shadow_offset,
            y - radius + shadow_offset,
            x + radius + shadow_offset,
            y + radius + shadow_offset,
        ),
        fill=(20, 34, 60, 70),
    )
    draw.ellipse(
        (x - radius, y - radius, x + radius, y + radius),
        fill=(37, 99, 235, 255),
        outline=(255, 255, 255, 255),
        width=max(3, radius // 8),
    )
    label = str(no)
    bbox = draw.textbbox((0, 0), label, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    draw.text((x - text_w / 2, y - text_h / 2 - radius * 0.04), label, fill=(255, 255, 255, 255), font=font)


def _resolve_marker_position(
    marker: dict[str, Any],
    width: int,
    height: int,
    radius: int,
    placed_rects: list[tuple[int, int, int, int]],
) -> tuple[int, int]:
    bbox = marker.get("target_bbox") if isinstance(marker.get("target_bbox"), dict) else {}
    candidates = _marker_position_candidates(bbox, marker.get("x_ratio"), marker.get("y_ratio"))
    for x_ratio, y_ratio in candidates:
        x = int(_clamp(float(x_ratio), radius / width, 1 - radius / width) * width)
        y = int(_clamp(float(y_ratio), radius / height, 1 - radius / height) * height)
        marker_rect = (x - radius, y - radius, x + radius, y + radius)
        if _overlaps_any(marker_rect, placed_rects, padding=max(2, radius // 4)):
            continue
        return x, y
    x = int(_clamp(float(marker.get("x_ratio") or 0.5), radius / width, 1 - radius / width) * width)
    y = int(_clamp(float(marker.get("y_ratio") or 0.5), radius / height, 1 - radius / height) * height)
    return x, y


def _marker_position_candidates(bbox: dict[str, Any], default_x: Any, default_y: Any) -> list[tuple[float, float]]:
    try:
        x1 = float(bbox.get("x1"))
        y1 = float(bbox.get("y1"))
        x2 = float(bbox.get("x2"))
        y2 = float(bbox.get("y2"))
    except Exception:
        return [(float(default_x or 0.5), float(default_y or 0.5))]
    if x2 <= x1 or y2 <= y1:
        return [(float(default_x or 0.5), float(default_y or 0.5))]
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    gap = 0.024
    return [
        (x1 + gap, y1 + gap),
        (x1 - gap, y1 + gap),
        (x1 + gap, cy),
        (x2 - gap, y1 + gap),
        (x2 + gap, y1 + gap),
        (cx, y1 + gap),
        (float(default_x or x1 + gap), float(default_y or y1 + gap)),
    ]


def _bbox_to_pixels(bbox: Any, width: int, height: int) -> tuple[int, int, int, int] | None:
    if not isinstance(bbox, dict):
        return None
    try:
        x1 = int(_clamp(float(bbox.get("x1")), 0.0, 1.0) * width)
        y1 = int(_clamp(float(bbox.get("y1")), 0.0, 1.0) * height)
        x2 = int(_clamp(float(bbox.get("x2")), 0.0, 1.0) * width)
        y2 = int(_clamp(float(bbox.get("y2")), 0.0, 1.0) * height)
    except Exception:
        return None
    if x2 <= x1 or y2 <= y1:
        return None
    return (x1, y1, x2, y2)


def _overlaps_any(
    rect: tuple[int, int, int, int],
    others: list[tuple[int, int, int, int]],
    *,
    padding: int = 0,
) -> bool:
    left, top, right, bottom = rect
    for other_left, other_top, other_right, other_bottom in others:
        if right + padding <= other_left or other_right + padding <= left:
            continue
        if bottom + padding <= other_top or other_bottom + padding <= top:
            continue
        return True
    return False


def _bbox_marker_x(bbox: dict[str, Any], default: Any) -> Any:
    try:
        x1 = float(bbox.get("x1"))
        x2 = float(bbox.get("x2"))
        return _clamp((x1 + 0.024) if x2 > x1 else (x1 + x2) / 2, 0.03, 0.97)
    except Exception:
        return default


def _bbox_marker_y(bbox: dict[str, Any], default: Any) -> Any:
    try:
        y1 = float(bbox.get("y1"))
        y2 = float(bbox.get("y2"))
        return _clamp((y1 + 0.024) if y2 > y1 else (y1 + y2) / 2, 0.03, 0.97)
    except Exception:
        return default


def _is_marker_candidate(area: dict[str, Any]) -> bool:
    component_type = str(area.get("component_type") or area.get("type") or "unknown").strip().lower()
    if component_type == "unknown":
        return False
    name = _clean_text(area.get("name") or area.get("component_name") or area.get("title"))
    texts = [_clean_text(value) for value in area.get("visible_texts", []) or area.get("texts", []) or []]
    texts = [text for text in texts if _is_usable_text(text)]
    if _is_brand_component(area, name, texts) or _is_global_header_component(area, name, texts) or _is_generic_ui_word(name):
        return False
    joined = " ".join([name, *texts]).strip()
    if not joined or _looks_like_file_stem(joined) or _noise_ratio(joined) > 0.35:
        return False
    if component_type == "content" and len(texts) < 2 and len(name) < 3:
        return False
    return True


def _clean_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    text = text.replace("아시 Platform", "AI Platform")
    text = re.sub(r"\bSaori\b", "AI", text, flags=re.IGNORECASE)
    text = re.sub(r"SQL[- ]?Pytho\b", "SQL-Python", text, flags=re.IGNORECASE)
    return text.strip(" \t\r\n.,;:|/\\[]{}()<>")


def _is_usable_text(text: str) -> bool:
    text = _clean_text(text)
    if _looks_like_file_stem(text):
        return False
    if len(text) == 1 and text not in {"홈"}:
        return False
    if re.fullmatch(r"[\W_]+", text) or re.fullmatch(r"[\d\s%.,:-]+", text):
        return False
    if not re.search(r"[가-힣A-Za-z]", text):
        return False
    if len(text) <= 3 and re.fullmatch(r"[A-Za-z]{1,3}", text):
        return text.lower() in {"ai", "id", "api", "sql"}
    if _is_generic_ui_word(text):
        return False
    return True


def _looks_like_file_stem(text: str) -> bool:
    return bool(re.match(r"^\d{1,3}[_-][가-힣A-Za-z0-9_ -]+$", _clean_text(text)))


def _noise_ratio(text: str) -> float:
    if not text:
        return 1.0
    noisy = len(re.findall(r"[^가-힣A-Za-z0-9\s]", text))
    return noisy / max(1, len(text))


def _is_brand_component(area: dict[str, Any], name: str, texts: list[str]) -> bool:
    joined = " ".join([name, *texts]).strip().lower()
    bbox = area.get("bbox") if isinstance(area.get("bbox"), dict) else {}
    x1 = float(bbox.get("x1", 1.0) or 1.0)
    y1 = float(bbox.get("y1", 1.0) or 1.0)
    if any(token in joined for token in ("sf ai platform", "ai platform", "on-premise genai portal")) and x1 < 0.25 and y1 < 0.2:
        return True
    return joined in {"ai platform", "sf ai platform"}


def _is_global_header_component(area: dict[str, Any], name: str, texts: list[str]) -> bool:
    bbox = area.get("bbox") if isinstance(area.get("bbox"), dict) else {}
    try:
        x1 = float(bbox.get("x1", 1.0) or 1.0)
        y1 = float(bbox.get("y1", 1.0) or 1.0)
    except Exception:
        return False
    joined = " ".join([name, *texts]).lower()
    header_tokens = ("통합 검색", "검색", "권한", "kms", "전략부", "부서", "로그인")
    return y1 < 0.14 and x1 > 0.58 and any(token in joined for token in header_tokens)


def _is_generic_ui_word(text: str) -> bool:
    return _clean_text(text).lower() in {
        "서비스",
        "부서별",
        "문서",
        "사용자",
        "관리",
        "정보",
        "상태",
        "플랫폼",
        "platform",
    }


def _screen_menu_levels(screen_name: str) -> tuple[str, str]:
    name = re.sub(r"^\d{1,3}_", "", str(screen_name or "").strip())
    parts = [part for part in name.split("_") if part]
    if len(parts) >= 2:
        return " ".join(parts[:-1]), parts[-1]
    return name or "업무", name or "화면"
