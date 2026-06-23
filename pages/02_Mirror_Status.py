from pathlib import Path
import subprocess

import streamlit as st


ROOT_DIR = Path(__file__).resolve().parents[1]
UPSTREAM_SHA = "0cabfcd8db6015689c34ec23cb0afed8cae312bb"


def _git_output(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=ROOT_DIR,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        ).strip()
    except Exception:
        return "Unavailable"


def _exists(path: str) -> str:
    return "Ready" if (ROOT_DIR / path).exists() else "Missing"


def main() -> None:
    st.set_page_config(page_title="ALPLED Mirror Status", layout="wide")

    st.title("ALPLED Mirror Status")
    st.caption("Upstream mirror metadata and preserved deployment overlays.")

    head_sha = _git_output("rev-parse", "HEAD")
    branch = _git_output("branch", "--show-current")

    col1, col2, col3 = st.columns(3)
    col1.metric("Branch", branch)
    col2.metric("Local commit", head_sha[:7] if head_sha != "Unavailable" else head_sha)
    col3.metric("Upstream commit", UPSTREAM_SHA[:7])

    st.subheader("Mirror Inputs")
    st.table(
        [
            {"Item": "Upstream repository", "Value": "SKN24-FINAL-3TEAM/ALPLED-CORE"},
            {"Item": "Upstream SHA", "Value": UPSTREAM_SHA},
            {"Item": "Destination repository", "Value": "junhaj27-jpg/jun"},
            {"Item": "Mirror commit", "Value": head_sha},
        ]
    )

    st.subheader("Preserved Overlays")
    st.table(
        [
            {"Path": "pages/01_Project_Status.py", "Status": _exists("pages/01_Project_Status.py")},
            {"Path": "pages/02_Mirror_Status.py", "Status": _exists("pages/02_Mirror_Status.py")},
            {"Path": "requirements.txt", "Status": _exists("requirements.txt")},
            {"Path": ".gitignore", "Status": _exists(".gitignore")},
        ]
    )

    st.subheader("Publish")
    st.code("git push origin main", language="bash")


if __name__ == "__main__":
    main()
