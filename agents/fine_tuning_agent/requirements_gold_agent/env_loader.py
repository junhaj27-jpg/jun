from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ENV_FILE = REPO_ROOT / ".env"


def load_runtime_env(
    env_file: str | Path,
    *,
    override: bool = False,
    project_env_file: str | Path | None = None,
) -> Path | None:
    primary = Path(env_file)
    fallback = Path(project_env_file) if project_env_file is not None else PROJECT_ENV_FILE

    if primary.exists():
        load_dotenv(primary, override=override)
        return primary

    if fallback.exists():
        load_dotenv(fallback, override=override)
        return fallback

    return None
