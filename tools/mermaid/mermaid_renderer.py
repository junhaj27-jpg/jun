import subprocess
from pathlib import Path

from config.settings import Settings, get_settings
from tools.result import ToolResult, error_result, success_result


def render_mermaid(
    mermaid_code: str,
    *,
    file_stem: str = "diagram",
    output_dir: str | Path | None = None,
    settings: Settings | None = None,
    render_width: int | None = None,
    render_height: int | None = None,
    render_scale: int | None = None,
) -> ToolResult:
    settings = settings or get_settings()
    destination = Path(output_dir or settings.mermaid_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    mermaid_path = destination / f"{file_stem}.mmd"
    image_path = destination / f"{file_stem}.png"
    mermaid_path.write_text(mermaid_code, encoding="utf-8")
    cli_path = settings.mermaid_cli_path
    render_width = int(render_width or settings.mermaid_render_width)
    render_height = int(render_height or settings.mermaid_render_height)
    render_scale = int(render_scale or settings.mermaid_render_scale)
    try:
        completed = subprocess.run(
            [
                cli_path,
                "-i",
                str(mermaid_path),
                "-o",
                str(image_path),
                "-w",
                str(render_width),
                "-H",
                str(render_height),
                "-s",
                str(render_scale),
                "-b",
                "white",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if completed.returncode != 0 or not image_path.exists():
            return error_result(
                "MERMAID_RENDER_FAILED",
                completed.stderr.strip() or "Mermaid 이미지 렌더링에 실패했습니다.",
                {"mermaid_file_path": str(mermaid_path)},
            )
        return success_result(
            {
                "mermaid_file_path": str(mermaid_path),
                "mermaid_image_path": str(image_path),
                "render_options": {
                    "width": render_width,
                    "height": render_height,
                    "scale": render_scale,
                },
            }
        )
    except Exception as exc:
        return error_result(
            "MERMAID_RENDER_FAILED",
            str(exc),
            {"mermaid_file_path": str(mermaid_path)},
        )
