from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from .pipeline import run_document, run_file
from .runtime import get_runtime


class RequirementsGenerationService:
    """외부 서비스가 사용하는 단일 진입점. 내부 멀티에이전트 TASK 구성은 감추고 GOLD 요구사항명세서를 반환한다."""

    _instance: "RequirementsGenerationService | None" = None
    _instance_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "RequirementsGenerationService":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def warmup(self) -> None:
        """서버 시작 시 기본 모델과 stage1 어댑터, 학습 프롬프트를 미리 로드한다."""
        get_runtime().start()

    def generate_from_dict(self, document: dict[str, Any], *, output_dir: Path | str | None = None, job_id: str | None = None, replace_existing: bool = True) -> dict:
        return run_document(document, output_dir=output_dir, run_id=job_id, replace_existing=replace_existing)

    def generate_from_file(self, input_path: Path | str, *, output_dir: Path | str | None = None, job_id: str | None = None, replace_existing: bool = True) -> dict:
        return run_file(input_path, output_dir=output_dir, run_id=job_id, replace_existing=replace_existing)
