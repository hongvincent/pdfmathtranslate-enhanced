from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image
from PIL import ImageSequence
from PIL import UnidentifiedImageError

PDF_SIGNATURE = b"%PDF-"
DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

SUPPORTED_IMAGE_EXTENSIONS = {
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}
SUPPORTED_OFFICE_EXTENSIONS = {
    ".csv",
    ".doc",
    ".docm",
    ".docx",
    ".odp",
    ".ods",
    ".odt",
    ".ppt",
    ".pptm",
    ".pptx",
    ".rtf",
    ".tsv",
    ".txt",
    ".xls",
    ".xlsm",
    ".xlsx",
}
SUPPORTED_IMAGE_CONTENT_TYPES = {
    "image/bmp",
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
}
SUPPORTED_OFFICE_CONTENT_TYPES = {
    "application/msword",
    "application/rtf",
    "application/vnd.ms-excel",
    "application/vnd.ms-excel.sheet.macroenabled.12",
    "application/vnd.ms-powerpoint",
    "application/vnd.ms-powerpoint.presentation.macroenabled.12",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    DOCX_CONTENT_TYPE,
    "application/vnd.oasis.opendocument.presentation",
    "application/vnd.oasis.opendocument.spreadsheet",
    "application/vnd.oasis.opendocument.text",
    "text/csv",
    "text/plain",
    "text/rtf",
    "text/tab-separated-values",
}
CONTENT_TYPE_SUFFIXES = {
    "application/msword": ".doc",
    "application/rtf": ".rtf",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.ms-excel.sheet.macroenabled.12": ".xlsm",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.ms-powerpoint.presentation.macroenabled.12": ".pptm",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    DOCX_CONTENT_TYPE: ".docx",
    "application/vnd.oasis.opendocument.presentation": ".odp",
    "application/vnd.oasis.opendocument.spreadsheet": ".ods",
    "application/vnd.oasis.opendocument.text": ".odt",
    "image/bmp": ".bmp",
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/tiff": ".tiff",
    "image/webp": ".webp",
    "text/csv": ".csv",
    "text/plain": ".txt",
    "text/rtf": ".rtf",
    "text/tab-separated-values": ".tsv",
}
SUPPORTED_UPLOAD_LABEL = (
    "PDF, DOC, DOCX, PPT, PPTX, XLS, XLSX, ODT, ODS, ODP, RTF, TXT, CSV, "
    "PNG, JPG, JPEG, BMP, TIFF, WEBP"
)


class UnsupportedInputError(ValueError):
    pass


@dataclass(frozen=True)
class PreparedInputFile:
    path: Path
    original_name: str
    storage_name: str
    converted: bool = False


def _normalize_content_type(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def _safe_stem(filename: str) -> str:
    stem = Path(filename).stem or Path(filename).name or "document"
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in stem)
    return safe.strip("._") or "document"


def _target_pdf_name(filename: str) -> str:
    return f"{_safe_stem(filename)}.pdf"


def _guess_suffix(filename: str, content_type: str | None = None) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix:
        return suffix
    return CONTENT_TYPE_SUFFIXES.get(_normalize_content_type(content_type), "")


def _is_pdf_bytes(header: bytes) -> bool:
    return header.startswith(PDF_SIGNATURE)


def _is_supported_image(filename: str, content_type: str | None = None) -> bool:
    suffix = _guess_suffix(filename, content_type)
    normalized_content_type = _normalize_content_type(content_type)
    return (
        suffix in SUPPORTED_IMAGE_EXTENSIONS
        or normalized_content_type in SUPPORTED_IMAGE_CONTENT_TYPES
    )


def _is_supported_office(filename: str, content_type: str | None = None) -> bool:
    suffix = _guess_suffix(filename, content_type)
    normalized_content_type = _normalize_content_type(content_type)
    return (
        suffix in SUPPORTED_OFFICE_EXTENSIONS
        or normalized_content_type in SUPPORTED_OFFICE_CONTENT_TYPES
    )


def _flatten_image(frame: Image.Image) -> Image.Image:
    rgba = frame.convert("RGBA")
    background = Image.new("RGB", rgba.size, "white")
    background.paste(rgba, mask=rgba.getchannel("A"))
    return background


def _convert_image_to_pdf(image: Image.Image, output_path: Path) -> None:
    frames = [_flatten_image(frame) for frame in ImageSequence.Iterator(image)]
    if not frames:
        frames = [_flatten_image(image)]
    first, *rest = frames
    try:
        first.save(output_path, "PDF", save_all=True, append_images=rest, resolution=300.0)
    finally:
        for frame in frames:
            frame.close()


def _convert_image_bytes_to_pdf(content: bytes, output_path: Path, original_name: str) -> None:
    try:
        with Image.open(BytesIO(content)) as image:
            _convert_image_to_pdf(image, output_path)
    except UnidentifiedImageError as exc:
        raise UnsupportedInputError(
            f"Automatic PDF conversion failed for {original_name}. "
            "The image file could not be decoded."
        ) from exc


def _convert_image_file_to_pdf(source_path: Path, output_path: Path, original_name: str) -> None:
    try:
        with Image.open(source_path) as image:
            _convert_image_to_pdf(image, output_path)
    except UnidentifiedImageError as exc:
        raise UnsupportedInputError(
            f"Automatic PDF conversion failed for {original_name}. "
            "The image file could not be decoded."
        ) from exc


def _run_soffice_conversion(source_path: Path, output_dir: Path, original_name: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    home_dir = output_dir / "soffice-home"
    home_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "soffice",
        "--headless",
        "--nologo",
        "--nodefault",
        "--nofirststartwizard",
        "--nolockcheck",
        "--convert-to",
        "pdf",
        "--outdir",
        str(output_dir),
        str(source_path),
    ]
    env = {
        **os.environ,
        "HOME": str(home_dir),
    }
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
            check=False,
        )
    except FileNotFoundError as exc:
        raise UnsupportedInputError(
            f"Automatic PDF conversion for {original_name} requires LibreOffice in the runtime image."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise UnsupportedInputError(
            f"Automatic PDF conversion timed out for {original_name}."
        ) from exc

    output_path = output_dir / f"{source_path.stem}.pdf"
    if result.returncode != 0 or not output_path.exists():
        details = (result.stderr or result.stdout or "").strip()
        if not details:
            details = "LibreOffice did not return a usable PDF output."
        raise UnsupportedInputError(
            f"Automatic PDF conversion failed for {original_name}: {details}"
        )
    return output_path


def _unsupported_upload_message(filename: str) -> str:
    return (
        f"{filename} is not supported for automatic conversion. "
        f"Upload a PDF or one of: {SUPPORTED_UPLOAD_LABEL}."
    )


def prepare_uploaded_file(
    filename: str,
    content: bytes,
    content_type: str | None,
    working_dir: Path,
) -> PreparedInputFile:
    working_dir.mkdir(parents=True, exist_ok=True)
    header = content[: len(PDF_SIGNATURE)]
    normalized_content_type = _normalize_content_type(content_type)
    pdf_path = working_dir / _target_pdf_name(filename)

    if _is_pdf_bytes(header):
        pdf_path.write_bytes(content)
        return PreparedInputFile(pdf_path, filename, pdf_path.name, converted=False)

    if _guess_suffix(filename, content_type) == ".pdf" or normalized_content_type == "application/pdf":
        raise UnsupportedInputError(
            f"{filename} is not a valid PDF file. Only valid PDFs or auto-convertible files can be queued."
        )

    if _is_supported_image(filename, content_type):
        _convert_image_bytes_to_pdf(content, pdf_path, filename)
        return PreparedInputFile(pdf_path, filename, pdf_path.name, converted=True)

    if _is_supported_office(filename, content_type):
        source_suffix = _guess_suffix(filename, content_type) or ".bin"
        source_path = working_dir / f"source{source_suffix}"
        source_path.write_bytes(content)
        converted_path = _run_soffice_conversion(source_path, working_dir, filename)
        return PreparedInputFile(converted_path, filename, pdf_path.name, converted=True)

    raise UnsupportedInputError(_unsupported_upload_message(filename))


def prepare_retry_source_file(
    source_path: Path,
    original_name: str,
    working_dir: Path,
) -> PreparedInputFile:
    with source_path.open("rb") as handle:
        header = handle.read(len(PDF_SIGNATURE))

    pdf_name = _target_pdf_name(original_name)
    if _is_pdf_bytes(header):
        return PreparedInputFile(source_path, original_name, pdf_name, converted=False)

    working_dir.mkdir(parents=True, exist_ok=True)
    output_path = working_dir / pdf_name

    if _is_supported_image(original_name):
        _convert_image_file_to_pdf(source_path, output_path, original_name)
        return PreparedInputFile(output_path, original_name, pdf_name, converted=True)

    if _is_supported_office(original_name):
        converted_path = _run_soffice_conversion(source_path, working_dir, original_name)
        return PreparedInputFile(converted_path, original_name, pdf_name, converted=True)

    raise UnsupportedInputError(
        f"{original_name} is not supported for automatic conversion during retry. "
        f"Upload a PDF or one of: {SUPPORTED_UPLOAD_LABEL}."
    )
