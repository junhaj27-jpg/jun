from pathlib import Path

import streamlit as st


ROOT_DIR = Path(__file__).resolve().parents[1]
REQUIREMENTS_PATH = ROOT_DIR / "requirements.txt"


def _read_requirements() -> list[str]:
    if not REQUIREMENTS_PATH.exists():
        return []

    return [
        line.strip()
        for line in REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _path_status(path: str) -> str:
    target = ROOT_DIR / path
    return "Ready" if target.exists() else "Missing"


def main() -> None:
    st.set_page_config(page_title="ALPLED Project Status", layout="wide")

    st.title("ALPLED Project Status")
    st.caption("Runtime readiness, generated artifacts, and local setup overview.")

    col1, col2, col3 = st.columns(3)
    col1.metric("Python dependencies", len(_read_requirements()))
    col2.metric("Generated output folder", _path_status("output"))
    col3.metric("Temporary JSON folder", _path_status("json_temp"))

    st.subheader("Runtime Checklist")
    st.table(
        [
            {"Item": "Python requirements", "Status": _path_status("requirements.txt")},
            {"Item": "Qdrant storage", "Status": _path_status("qdrant_storage")},
            {"Item": "Generated outputs", "Status": _path_status("output")},
            {"Item": "Temporary JSON files", "Status": _path_status("json_temp")},
            {"Item": "SRS document generator", "Status": _path_status("SRS/req_agent/package.json")},
        ]
    )

    st.subheader("Install")
    st.code("pip install -r requirements.txt", language="bash")
    st.code("cd SRS/req_agent && npm install", language="bash")

    st.subheader("Environment")
    st.code(
        "\n".join(
            [
                "QDRANT_URL=http://localhost:6333",
                "QDRANT_COLLECTION=arkive",
                "EMBED_MODEL_NAME=BAAI/bge-m3",
                "LLM_BASE_URL=http://localhost:11434/v1",
                "LLM_MODEL_NAME=qwen3:1.7b",
                "LLM_API_KEY=EMPTY",
            ]
        ),
        language="dotenv",
    )

    with st.expander("requirements.txt"):
        st.write(_read_requirements())


if __name__ == "__main__":
    main()
