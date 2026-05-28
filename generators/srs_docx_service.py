import json
import os
import subprocess
from pathlib import Path
from datetime import datetime

_JS_PATH  = Path(__file__).parent / "srs_gen_req_docx.js"
_OUT_DIR  = Path(__file__).parent.parent / "output"
_ROOT_DIR = Path(__file__).parent
_PROJECT_ROOT = Path(__file__).parent.parent


def generate_docx(reqs: list[dict], prefix: str = "requirements") -> str:
    _OUT_DIR.mkdir(exist_ok=True)

    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = _OUT_DIR / f"{prefix}_{ts}.docx"

    clean    = [{k: v for k, v in r.items() if not k.startswith("_")} for r in reqs]

    # tmp 파일을 한글 없는 req_agent 루트에 저장
    tmp_json = _ROOT_DIR / f"_tmp_{ts}.json"
    tmp_js   = _ROOT_DIR / f"_tmp_{ts}.js"

    tmp_json.write_text(json.dumps(clean, ensure_ascii=False), encoding="utf-8")

    script = _JS_PATH.read_text(encoding="utf-8")
    script = script.replace(
        "'/home/claude/sample_reqs.json'",
        repr(tmp_json.as_posix())
    ).replace(
        "'/home/claude/requirements_definition.docx'",
        repr(out_path.as_posix())
    )

    tmp_js.write_text(script, encoding="utf-8")

    try:
        env = os.environ.copy()
        node_paths = [
            _PROJECT_ROOT / "node_modules",
            _PROJECT_ROOT / "SRS" / "req_agent" / "node_modules",
        ]
        existing_node_path = env.get("NODE_PATH")
        env["NODE_PATH"] = os.pathsep.join(
            [str(path) for path in node_paths if path.exists()]
            + ([existing_node_path] if existing_node_path else [])
        )
        result = subprocess.run(
            ["node", tmp_js.name],   # 파일명만 (cwd 기준)
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(_ROOT_DIR),
            env=env,
        )
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print("=== Node.js 에러 ===")
        print(e.stderr)
        raise
    finally:
        tmp_json.unlink(missing_ok=True)
        tmp_js.unlink(missing_ok=True)

    return str(out_path)
