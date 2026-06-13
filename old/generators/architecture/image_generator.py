import os
import re
import shutil
import subprocess
from pathlib import Path

from agents.arch_nodes.common import normalize_mermaid_syntax
from generators.common.mermaid_renderer import find_puppeteer_browser, render_mermaid_ink_image


def render_mermaid_image(
    mermaid_script: str,
    *,
    output_mmd_path: str = "./mmd_temp/architecture_diagram.mmd",
    output_image_path: str = "./output/architecture_diagram.png",
) -> tuple[str, str | None]:
    mmd_path = Path(output_mmd_path)
    image_path = Path(output_image_path)
    mmd_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.parent.mkdir(parents=True, exist_ok=True)

    clean_script = normalize_mermaid_syntax(mermaid_script)
    mmd_path.write_text(clean_script, encoding="utf-8")

    if not clean_script:
        fallback_path = render_basic_architecture_image(clean_script, str(image_path))
        return str(mmd_path), fallback_path

    ink_path = render_mermaid_ink_image(clean_script, str(image_path))
    if ink_path:
        return str(mmd_path), ink_path

    mmdc_path = (
        os.getenv("MMDC_PATH")
        or shutil.which("mmdc")
        or r"C:\Users\Playdata\AppData\Roaming\npm\mmdc.cmd"
    )
    env = os.environ.copy()
    puppeteer_executable_path = env.get("PUPPETEER_EXECUTABLE_PATH") or find_puppeteer_browser()
    if puppeteer_executable_path:
        env["PUPPETEER_EXECUTABLE_PATH"] = puppeteer_executable_path

    try:
        subprocess.run(
            [
                mmdc_path,
                "-i",
                str(mmd_path),
                "-o",
                str(image_path),
                "-b",
                "white",
            ],
            check=True,
            env=env,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(f"[WARN] Architecture Mermaid 이미지 생성 실패: {exc}")
        fallback_path = render_basic_architecture_image(clean_script, str(image_path))
        return str(mmd_path), fallback_path

    return str(mmd_path), str(image_path)


def render_basic_architecture_image(mermaid_script: str, output_image_path: str) -> str | None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as exc:
        print(f"[WARN] Pillow fallback 이미지 생성 실패: {exc}")
        return None

    nodes, edges = _parse_mermaid_nodes_and_edges(mermaid_script)
    if not nodes:
        nodes = {
            "USER": "User",
            "WEB": "Web Server",
            "WAS": "Application Server",
            "DB": "Database",
        }
        edges = [("USER", "WEB"), ("WEB", "WAS"), ("WAS", "DB")]

    node_ids = list(nodes.keys())[:12]
    width = 1200
    height = max(520, 160 + len(node_ids) * 90)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    try:
        font_title = ImageFont.truetype("malgun.ttf", 28)
        font = ImageFont.truetype("malgun.ttf", 18)
        font_small = ImageFont.truetype("malgun.ttf", 14)
    except Exception:
        font_title = ImageFont.load_default()
        font = ImageFont.load_default()
        font_small = ImageFont.load_default()

    draw.text((40, 30), "시스템 아키텍처 다이어그램", fill="#1f2937", font=font_title)

    positions = {}
    x_positions = [120, 390, 660, 930]
    for idx, node_id in enumerate(node_ids):
        col = idx % len(x_positions)
        row = idx // len(x_positions)
        x = x_positions[col]
        y = 110 + row * 140
        positions[node_id] = (x, y)
        _draw_box(draw, x, y, 190, 72, nodes[node_id], font)

    for from_id, to_id in edges:
        if from_id not in positions or to_id not in positions:
            continue
        x1, y1 = positions[from_id]
        x2, y2 = positions[to_id]
        _draw_arrow(draw, (x1 + 190, y1 + 36), (x2, y2 + 36))

    draw.text(
        (40, height - 45),
        "Mermaid CLI 렌더링 실패 시 생성되는 기본 이미지입니다.",
        fill="#6b7280",
        font=font_small,
    )

    output_path = Path(output_image_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return str(output_path)


def _parse_mermaid_nodes_and_edges(mermaid_script: str) -> tuple[dict[str, str], list[tuple[str, str]]]:
    nodes = {}
    edges = []
    edge_pattern = re.compile(r"^\s*([A-Za-z0-9_]+)\s*[-.=ox|{}]+>\s*([A-Za-z0-9_]+)")
    node_pattern = re.compile(r"([A-Za-z0-9_]+)\s*(?:\[([^\]]+)\]|\(\(([^\)]+)\)\)|\(\[?([^\)]+)\]?\))")

    for line in mermaid_script.splitlines():
        line = line.strip()
        if not line or line.startswith(("flowchart", "graph", "subgraph", "end")):
            continue

        edge_match = edge_pattern.search(line)
        if edge_match:
            edges.append((edge_match.group(1), edge_match.group(2)))

        for node_id, label1, label2, label3 in node_pattern.findall(line):
            label = label1 or label2 or label3 or node_id
            nodes.setdefault(node_id, label.strip('"'))

    return nodes, edges


def _draw_box(draw, x: int, y: int, width: int, height: int, text: str, font) -> None:
    draw.rounded_rectangle((x, y, x + width, y + height), radius=12, fill="#eef2ff", outline="#4f46e5", width=2)
    wrapped = _wrap_text(text, 18)
    for idx, line in enumerate(wrapped[:3]):
        draw.text((x + 14, y + 14 + idx * 20), line, fill="#111827", font=font)


def _draw_arrow(draw, start: tuple[int, int], end: tuple[int, int]) -> None:
    sx, sy = start
    ex, ey = end
    draw.line((sx, sy, ex, ey), fill="#374151", width=2)
    draw.polygon([(ex, ey), (ex - 10, ey - 5), (ex - 10, ey + 5)], fill="#374151")


def _wrap_text(text: str, max_len: int) -> list[str]:
    value = str(text or "")
    return [value[i:i + max_len] for i in range(0, len(value), max_len)] or [""]
