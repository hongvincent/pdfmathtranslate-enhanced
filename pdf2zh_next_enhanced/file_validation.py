from __future__ import annotations

from pathlib import Path

PDF_SIGNATURE = b"%PDF-"
DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class UnsupportedInputError(ValueError):
    pass


def validate_uploaded_file(
    filename: str,
    header: bytes,
    content_type: str | None = None,
) -> None:
    suffix = Path(filename).suffix.lower()
    normalized_content_type = (content_type or "").lower()

    if suffix == ".docx" or normalized_content_type == DOCX_CONTENT_TYPE:
        raise UnsupportedInputError(
            f"{filename} is a DOCX file. This app currently accepts PDF input only. "
            "Convert the document to PDF before queueing it."
        )

    if suffix and suffix != ".pdf" and not header.startswith(PDF_SIGNATURE):
        raise UnsupportedInputError(
            f"{filename} is not a supported input file. Only PDF files can be queued right now."
        )

    if not header.startswith(PDF_SIGNATURE):
        raise UnsupportedInputError(
            f"{filename} is not a valid PDF file. Only PDF files can be queued right now."
        )


def validate_retry_source_file(filename: str, header: bytes) -> None:
    suffix = Path(filename).suffix.lower()

    if suffix == ".docx":
        raise UnsupportedInputError(
            f"{filename} is a DOCX file, so this job cannot be retried. "
            "Convert the document to PDF and submit it as a new job."
        )

    if suffix and suffix != ".pdf" and not header.startswith(PDF_SIGNATURE):
        raise UnsupportedInputError(
            f"{filename} is not a supported input file, so this job cannot be retried. "
            "Only PDF files can be submitted."
        )

    if not header.startswith(PDF_SIGNATURE):
        raise UnsupportedInputError(
            f"{filename} is not a valid PDF file, so this job cannot be retried. "
            "Submit a PDF source file as a new job instead."
        )
