"""Shared pytest fixtures for the DocWiz test suite.

No network or Groq API key is required for the whole suite (except the
explicitly-marked live test, which skips itself when no key is present).
"""
import uuid

import fitz  # PyMuPDF
import pytest

from app import create_app


def make_pdf(page_texts, scanned=False):
    """Build an in-memory PDF with one page per given text.

    scanned=True creates pages with no text (simulating image-only scans).
    """
    doc = fitz.open()
    for text in page_texts:
        page = doc.new_page()
        if not scanned and text:
            page.insert_text((72, 72), text, fontsize=11)
    return doc.tobytes()


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")  # keep tests offline-safe
    app = create_app(
        override_settings={
            "DATA_DIR": tmp_path,
            "UPLOAD_DIR": tmp_path / "uploads",
            "INDEX_DIR": tmp_path / "index",
            "GROQ_API_KEY": "",
            # Deterministic offline embedder: no network, no model download.
            "EMBEDDING_PROVIDER": "hashing",
            "EMBEDDING_CACHE": "0",  # don't write cache files in tmp dirs
            "TESTING": True,
        }
    )
    # make sure per-test data dirs exist
    (tmp_path / "uploads").mkdir(parents=True, exist_ok=True)
    (tmp_path / "index").mkdir(parents=True, exist_ok=True)
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def sample_two_page_pdf():
    return make_pdf(
        [
            "Photosynthesis converts light energy into chemical energy. "
            "Chlorophyll in plant chloroplasts absorbs photons, driving the synthesis of ATP. "
            "The light-dependent reactions occur in the thylakoid membranes.",
            "The Calvin cycle fixes carbon dioxide into glucose. "
            "It runs in the stroma and uses the ATP and NADPH produced earlier. "
            "RuBisCO is the key enzyme of carbon fixation.",
        ]
    )


@pytest.fixture()
def unique_name():
    return f"doc_{uuid.uuid4().hex[:6]}.pdf"
