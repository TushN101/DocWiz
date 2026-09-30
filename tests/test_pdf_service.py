"""Tests for PDF validation and extraction (no network, no model)."""
import io

import pytest

from app.utils.errors import AppError
from app.services import pdf_service
from tests.conftest import make_pdf


class FakeStorage:
    """Mimics werkzeug FileStorage for validate_upload()."""

    def __init__(self, data=b"", filename="", mimetype="application/pdf"):
        self.stream = io.BytesIO(data)
        self.filename = filename
        self.mimetype = mimetype

    def read(self):
        return self.stream.read()


def test_rejects_non_pdf_extension():
    with pytest.raises(AppError) as err:
        pdf_service.validate_upload(FakeStorage(b"hello", "notes.txt"), max_upload_mb=30)
    assert err.value.code == "invalid_file_type"


def test_rejects_renamed_text_file():
    with pytest.raises(AppError) as err:
        pdf_service.validate_upload(
            FakeStorage(b"just text, not a pdf at all", "fake.pdf"), 30
        )
    assert err.value.code == "not_a_real_pdf"


def test_rejects_empty_file():
    with pytest.raises(AppError) as err:
        pdf_service.validate_upload(FakeStorage(b"", "empty.pdf"), 30)
    assert err.value.code == "empty_file"


def test_rejects_oversized_file():
    big = b"%PDF-1.4\n" + b"x" * (2 * 1024 * 1024)
    with pytest.raises(AppError) as err:
        pdf_service.validate_upload(FakeStorage(big, "big.pdf"), max_upload_mb=1)
    assert err.value.code == "file_too_large"


def test_accepts_valid_pdf(sample_two_page_pdf):
    data = pdf_service.validate_upload(FakeStorage(sample_two_page_pdf, "bio.pdf"), 30)
    assert data.startswith(b"%PDF")


def test_extract_preserves_page_boundaries(sample_two_page_pdf):
    pages, info = pdf_service.extract_pages(sample_two_page_pdf, "bio.pdf", max_pages=200, min_total_chars=25, max_chars=1_500_000)
    assert [p["page"] for p in pages] == [1, 2]
    assert "Photosynthesis" in pages[0]["text"]
    assert "Calvin" in pages[1]["text"]
    assert info["total_pages"] == 2
    assert info["truncated"] is False


def test_extract_reports_scanned_pdf_as_no_text():
    scanned = make_pdf(["", ""], scanned=True)
    with pytest.raises(AppError) as err:
        pdf_service.extract_pages(scanned, "scan.pdf", max_pages=200, min_total_chars=25, max_chars=1_500_000)
    assert err.value.code == "no_extractable_text"
    assert "OCR" in err.value.message  # honest limitation messaging


def test_extract_handles_corrupt_pdf():
    garbage = b"%PDF-1.4 this is not really a pdf body \xff\xfe"
    with pytest.raises(AppError) as err:
        pdf_service.extract_pages(garbage, "broken.pdf", max_pages=200, min_total_chars=25, max_chars=1_500_000)
    assert err.value.code == "corrupt_pdf"


def test_extract_respects_page_cap():
    many = make_pdf([f"Page {i} talks about topic {i} with some filler text for extraction." for i in range(1, 31)])
    pages, info = pdf_service.extract_pages(many, "big.pdf", max_pages=5, min_total_chars=25, max_chars=1_500_000)
    assert len(pages) == 5
    assert info["truncated"] is True
    assert info["total_pages"] == 30
