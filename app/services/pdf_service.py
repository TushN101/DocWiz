"""PDF validation and page-aware text extraction (PyMuPDF / fitz).

Only PDFs are accepted. Validation layers:
  1. filename extension
  2. client MIME type (informational — browsers vary, so not decisive)
  3. magic bytes ("%PDF") — the reliable check
  4. structural parse + text extraction by fitz

Known, documented limitation: scanned/image-only PDFs have no extractable
text. DocWiz reports this honestly; it does NOT perform OCR.
"""
import logging

import fitz  # PyMuPDF

from app.utils.errors import AppError
from app.utils.text import normalize_text

logger = logging.getLogger("docwiz.pdf")

PDF_MAGIC = b"%PDF-"
_ALLOWED_MIMES = {
    "application/pdf",
    "application/x-pdf",
    "application/acrobat",
    "application/octet-stream",  # some browsers/OSes send this for .pdf
    "binary/octet-stream",
    "",  # absent content type — fall back to magic bytes
}


def validate_upload(file_storage, max_upload_mb: int) -> bytes:
    """Validate one uploaded file and return its raw bytes.

    Raises AppError with a user-facing message for every rejection.
    """
    original_name = file_storage.filename or ""
    if not original_name.lower().endswith(".pdf"):
        raise AppError("invalid_file_type", f"'{original_name or 'Unnamed file'}' is not a PDF. Only PDF files are supported.", 400)

    mime = (file_storage.mimetype or "").lower()
    if mime not in _ALLOWED_MIMES:
        raise AppError("invalid_file_type", f"'{original_name}' does not look like a PDF (unexpected content type).", 400)

    data = file_storage.read()
    if not data:
        raise AppError("empty_file", f"'{original_name}' is empty.", 400)
    if len(data) > max_upload_mb * 1024 * 1024:
        raise AppError(
            "file_too_large",
            f"'{original_name}' is larger than the {max_upload_mb} MB limit.",
            413,
        )
    if not data.lstrip()[:5] == PDF_MAGIC[:5]:
        # catches renamed .txt/.exe files that merely wear a .pdf extension
        raise AppError("not_a_real_pdf", f"'{original_name}' is not a valid PDF (corrupted or renamed file).", 400)
    return data


def extract_pages(data: bytes, display_name: str, max_pages: int, min_total_chars: int, max_chars: int):
    """Extract per-page text. Returns (pages, info).

    pages: [{"page": 1-based page number, "text": normalized text}, ...]
    info:  {"total_pages": int, "processed_pages": int, "truncated": bool,
            "empty_pages": [page numbers with no text], "char_count": int}

    Raises AppError for corrupt or text-free documents.
    """
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # fitz raises several exception types for corrupt files
        logger.info("Failed to open PDF %s: %s", display_name, exc)
        raise AppError("corrupt_pdf", f"'{display_name}' could not be opened — the file appears to be corrupted.", 400) from exc

    try:
        total_pages = doc.page_count
        if total_pages == 0:
            raise AppError("empty_pdf", f"'{display_name}' contains no pages.", 400)

        limit = min(total_pages, max_pages)
        pages, empty_pages = [], []
        char_count = 0
        for index in range(limit):
            try:
                raw = doc[index].get_text("text")
            except Exception:
                raw = ""
            text = normalize_text(raw or "")
            if text:
                char_count += len(text)
            else:
                empty_pages.append(index + 1)
            pages.append({"page": index + 1, "text": text})
            if char_count > max_chars:
                logger.info("Extraction char cap reached for %s at page %s", display_name, index + 1)
                pages = pages[: index + 1]
                break

        processed_pages = len(pages)
        truncated = processed_pages < total_pages
        if char_count < min_total_chars:
            detail = (
                f"'{display_name}' has no extractable text. It is likely a scanned or image-only PDF, "
                "and DocWiz does not perform OCR."
                if empty_pages
                else f"'{display_name}' contains no readable text."
            )
            raise AppError("no_extractable_text", detail, 400)

        info = {
            "total_pages": total_pages,
            "processed_pages": processed_pages,
            "truncated": truncated,
            "empty_pages": empty_pages,
            "char_count": char_count,
        }
        return pages, info
    finally:
        doc.close()
