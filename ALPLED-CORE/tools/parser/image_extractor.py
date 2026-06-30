import zipfile
from pathlib import Path

from config.settings import get_settings
from tools.result import ToolResult, error_result, success_result


def extract_images(file_path: str, output_dir: str | None = None) -> ToolResult:
    path = Path(file_path).resolve()
    destination = Path(
        output_dir or get_settings().extract_image_dir
    ).resolve()

    try:
        path.resolve(strict=True)
        destination.mkdir(parents=True, exist_ok=True)
        extension = path.suffix.lower()
        if extension == ".docx":
            images = _extract_docx_images(path, destination)
        elif extension == ".pdf":
            images = _extract_pdf_images(path, destination)
        else:
            return error_result(
                "IMAGE_EXTRACT_UNSUPPORTED",
                f"이미지 추출을 지원하지 않는 형식입니다: {extension}",
            )
        return success_result({"file_path": str(path), "image_paths": images})
    except Exception as exc:
        return error_result("IMAGE_EXTRACT_FAILED", str(exc), {"file_path": file_path})


def _extract_docx_images(path: Path, destination: Path) -> list[str]:
    extracted: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.startswith("word/media/"):
                continue
            target = destination / f"{path.stem}_{Path(name).name}"
            target.write_bytes(archive.read(name))
            extracted.append(str(target))
    return extracted


def _extract_pdf_images(path: Path, destination: Path) -> list[str]:
    import fitz

    extracted: list[str] = []
    with fitz.open(str(path)) as document:
        for page_number, page in enumerate(document, start=1):
            for image_number, image in enumerate(page.get_images(full=True), start=1):
                image_data = document.extract_image(image[0])
                extension = image_data.get("ext", "bin")
                target = destination / (
                    f"{path.stem}_p{page_number}_i{image_number}.{extension}"
                )
                target.write_bytes(image_data["image"])
                extracted.append(str(target))
    return extracted
