import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
GENERATOR_DIR = Path(__file__).resolve().parent
JS_TEMPLATE_PATH = GENERATOR_DIR / "architecture_gen_docx.js"
SRS_NODE_MODULES = ROOT_DIR / "SRS" / "req_agent" / "node_modules"


def generate_architecture_docx_with_node(payload: dict[str, Any], output_docx_path: str) -> str:
    output_path = Path(output_docx_path)
    if not output_path.is_absolute():
        output_path = ROOT_DIR / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    tmp_json = GENERATOR_DIR / f"_tmp_arch_{ts}.json"
    tmp_js = GENERATOR_DIR / f"_tmp_arch_{ts}.js"

    tmp_json.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    script = JS_TEMPLATE_PATH.read_text(encoding="utf-8")
    script = script.replace("__ARCH_INPUT_JSON__", tmp_json.resolve().as_posix())
    script = script.replace("__ARCH_OUTPUT_DOCX__", output_path.resolve().as_posix())
    tmp_js.write_text(script, encoding="utf-8")

    env = os.environ.copy()
    if SRS_NODE_MODULES.exists():
        existing_node_path = env.get("NODE_PATH")
        env["NODE_PATH"] = (
            str(SRS_NODE_MODULES)
            if not existing_node_path
            else str(SRS_NODE_MODULES) + os.pathsep + existing_node_path
        )

    node_cmd = shutil.which("node") or r"C:\Users\Playdata\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"

    try:
        result = subprocess.run(
            [node_cmd, tmp_js.name],
            check=True,
            text=True,
            encoding="utf-8",
            capture_output=True,
            cwd=str(GENERATOR_DIR),
            env=env,
        )
        if result.stdout:
            print(result.stdout)
    except subprocess.CalledProcessError as exc:
        print("=== Architecture Node.js DOCX 생성 에러 ===")
        print(exc.stdout)
        print(exc.stderr)
        raise
    finally:
        tmp_json.unlink(missing_ok=True)
        tmp_js.unlink(missing_ok=True)

    return str(output_path)
