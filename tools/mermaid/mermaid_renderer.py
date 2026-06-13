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
) -> ToolResult:
    settings = settings or get_settings()
    destination = Path(output_dir or settings.mermaid_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    mermaid_path = destination / f"{file_stem}.mmd"
    image_path = destination / f"{file_stem}.png"
    mermaid_path.write_text(mermaid_code, encoding="utf-8")
    try:
        completed = subprocess.run(
            ["mmdc", "-i", str(mermaid_path), "-o", str(image_path)],
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
            }
        )
    except Exception as exc:
        return error_result(
            "MERMAID_RENDER_FAILED",
            str(exc),
            {"mermaid_file_path": str(mermaid_path)},
        )
