from typing import Any
import logging

from agents.architecture_analysis.processors.diagram_builder import (
    build_clean_architecture_mermaid_source,
)

logger = logging.getLogger(__name__)


def build_architecture_mermaid(structure: dict[str, Any]) -> str:
    """
    ARCH Mermaid 생성 운영용 wrapper.

    실제 다이어그램 생성 로직은
    agents.architecture_analysis.processors.diagram_builder 의
    build_clean_architecture_mermaid_source()를 단일 원본으로 사용한다.
    """

    if not isinstance(structure, dict):
        return _build_empty_architecture_mermaid()

    try:
        mermaid_code = build_clean_architecture_mermaid_source(
            structure,
            direction="LR",
            edge_label_mode="none",
            max_edges=16,
        )

        if _is_valid_mermaid_code(mermaid_code):
            return mermaid_code

    except Exception as exc:
        logger.warning("ARCH Mermaid build failed. error=%s", exc)

    return _build_empty_architecture_mermaid()


def _is_valid_mermaid_code(value: Any) -> bool:
    if not isinstance(value, str):
        return False

    code = value.strip()
    if not code:
        return False

    return code.startswith(("%%{init:", "flowchart ", "graph "))


def _build_empty_architecture_mermaid() -> str:
    return "\n".join(
        [
            "flowchart LR",
            '    EMPTY["아키텍처 구성 정보 없음"]',
        ]
    )