import os
import shutil
import subprocess
from pathlib import Path

from agents.arch_nodes.common import strip_mermaid_block
from generators.erd_docx_generator import find_puppeteer_browser


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

    clean_script = strip_mermaid_block(mermaid_script)
    mmd_path.write_text(clean_script, encoding="utf-8")

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
        return str(mmd_path), None

    return str(mmd_path), str(image_path)

