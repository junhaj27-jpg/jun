import os
import subprocess
from pathlib import Path
from shutil import which

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
    """
    Mermaid 코드를 PNG 이미지로 렌더링합니다.

    - UTF-8로 Mermaid 소스를 저장합니다.
    - Windows cp949 환경에서도 subprocess 출력 디코딩 오류가 나지 않도록 UTF-8 + replace로 고정합니다.
    - 기존 PNG가 남아 있어도 새 렌더 실패를 성공으로 오판하지 않도록 렌더링 전 기존 이미지를 삭제합니다.
    - ERD 분할 렌더링에서 넘기는 render_width/render_height/render_scale 옵션을 유지합니다.
    """

    settings = settings or get_settings()
    destination = Path(output_dir or settings.mermaid_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)

    mermaid_path = destination / f"{file_stem}.mmd"
    image_path = destination / f"{file_stem}.png"
    mermaid_path.write_text(mermaid_code or "", encoding="utf-8")

    if image_path.exists():
        image_path.unlink()

    cli_path = settings.mermaid_cli_path or "mmdc"
    resolved_cli_path = which(cli_path) or cli_path

    width = int(render_width or settings.mermaid_render_width)
    height = int(render_height or settings.mermaid_render_height)
    scale = int(render_scale or settings.mermaid_render_scale)

    command = [
        resolved_cli_path,
        "-i",
        str(mermaid_path),
        "-o",
        str(image_path),
        "-w",
        str(width),
        "-H",
        str(height),
        "-s",
        str(scale),
        "-b",
        "white",
    ]

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("LC_ALL", "C.UTF-8")
    env.setdefault("LANG", "C.UTF-8")

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
            env=env,
        )

        stdout_text = (completed.stdout or "").strip()
        stderr_text = (completed.stderr or "").strip()

        if completed.returncode != 0:
            return error_result(
                "MERMAID_RENDER_FAILED",
                stderr_text or stdout_text or "Mermaid 이미지 렌더링에 실패했습니다.",
                {
                    "mermaid_file_path": str(mermaid_path),
                    "mermaid_image_path": str(image_path),
                    "returncode": completed.returncode,
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                    "command": command,
                },
            )

        if not image_path.exists():
            return error_result(
                "MERMAID_IMAGE_NOT_CREATED",
                "Mermaid CLI는 성공 코드를 반환했지만 PNG 파일이 생성되지 않았습니다.",
                {
                    "mermaid_file_path": str(mermaid_path),
                    "mermaid_image_path": str(image_path),
                    "returncode": completed.returncode,
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                    "command": command,
                },
            )

        return success_result(
            {
                "mermaid_file_path": str(mermaid_path),
                "mermaid_image_path": str(image_path),
                "render_options": {
                    "width": width,
                    "height": height,
                    "scale": scale,
                    "background": "white",
                },
                "warnings": [],
            }
        )
    except subprocess.TimeoutExpired as exc:
        return error_result(
            "MERMAID_RENDER_TIMEOUT",
            "Mermaid 이미지 렌더링 시간이 초과되었습니다.",
            {
                "mermaid_file_path": str(mermaid_path),
                "mermaid_image_path": str(image_path),
                "timeout": exc.timeout,
                "command": command,
            },
        )
    except FileNotFoundError:
        return error_result(
            "MERMAID_CLI_NOT_FOUND",
            f"Mermaid CLI를 찾을 수 없습니다: {cli_path}",
            {
                "mermaid_file_path": str(mermaid_path),
                "mermaid_image_path": str(image_path),
                "command": command,
            },
        )
    except Exception as exc:
        return error_result(
            "MERMAID_RENDER_FAILED",
            str(exc),
            {
                "mermaid_file_path": str(mermaid_path),
                "mermaid_image_path": str(image_path),
                "command": command,
            },
        )
