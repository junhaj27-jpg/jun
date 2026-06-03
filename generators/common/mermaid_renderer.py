import base64
from pathlib import Path

import requests


def render_mermaid_ink_image(mermaid_code: str, output_image_path: str, *, timeout: int = 3) -> str | None:
    try:
        encoded = base64.b64encode(mermaid_code.encode("utf-8")).decode("utf-8")
        response = requests.get(f"https://mermaid.ink/img/{encoded}", timeout=timeout)
        response.raise_for_status()
        output_path = Path(output_image_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.content)
        return str(output_path)
    except Exception as exc:
        print(f"[WARN] Mermaid Ink 이미지 생성 실패: {exc}")
        return None


def find_puppeteer_browser() -> str | None:
    cache_dir = Path.home() / ".cache" / "puppeteer"
    candidates = []
    patterns = [
        "chrome-headless-shell/**/chrome-headless-shell.exe",
        "chrome/**/chrome.exe",
    ]

    for pattern in patterns:
        candidates.extend(path for path in cache_dir.glob(pattern) if path.is_file())

    if not candidates:
        return None

    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return str(candidates[0])
