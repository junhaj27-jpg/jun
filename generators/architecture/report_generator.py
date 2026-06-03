from pathlib import Path

from agents.arch_nodes.common import strip_mermaid_block
from generators.architecture.image_generator import render_mermaid_image
from generators.architecture.docx_generator import generate_architecture_docx


def generate_architecture_report(
    *,
    requirement_doc: dict | None = None,
    analyzed_reqs: list[dict] | None = None,
    report_specs: str,
    mermaid_script: str,
    user_infra_spec: dict | None = None,
    extracted_infra: dict | None = None,
    output_md_path: str | None = None,
    output_docx_path: str,
    output_image_path: str,
    render_image: bool = True,
) -> dict:
    image_path = None
    mmd_path = None
    if render_image:
        mmd_path, image_path = render_mermaid_image(
            mermaid_script,
            output_image_path=output_image_path,
        )

    md_path = None
    if output_md_path:
        md_path = Path(output_md_path)
        md_path.parent.mkdir(parents=True, exist_ok=True)

        image_section = ""
        if image_path:
            image_section = f"\n\n## 시스템 아키텍처 다이어그램\n\n![Architecture]({Path(image_path).as_posix()})"

        content = (
            f"{report_specs}\n"
            f"{image_section}\n\n"
            f"## Mermaid 원본\n\n"
            f"```mermaid\n{strip_mermaid_block(mermaid_script)}\n```\n"
        )
        md_path.write_text(content, encoding="utf-8")

    resolved_image_path = str(Path(image_path).resolve()) if image_path else None

    docx_path = generate_architecture_docx(
        {
            "requirement_doc": requirement_doc or {},
            "analyzed_reqs": analyzed_reqs or [],
            "report_specs": report_specs,
            "mermaid_script": strip_mermaid_block(mermaid_script),
            "image_path": resolved_image_path,
            "user_infra_spec": user_infra_spec or {},
            "extracted_infra": extracted_infra or {},
        },
        output_path=output_docx_path,
    )

    return {
        "md_path": str(md_path) if md_path else None,
        "docx_path": docx_path,
        "mmd_path": mmd_path,
        "image_path": image_path,
    }
