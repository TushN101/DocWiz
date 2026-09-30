"""Live Groq API test — runs ONLY when a real GROQ_API_KEY is present.

This test is skipped automatically in every other environment, and its
result is never fabricated: either it actually runs against Groq, or it
shows up as SKIPPED in the pytest report.
"""
import io
import os

import pytest

from tests.conftest import make_pdf

_REAL_KEY = os.environ.get("GROQ_API_KEY", "").strip()
_HAS_REAL_KEY = bool(_REAL_KEY) and _REAL_KEY != "your_groq_api_key_here"

pytestmark = pytest.mark.skipif(
    not _HAS_REAL_KEY,
    reason="No real GROQ_API_KEY available — live integration test NOT EXECUTED (not failed).",
)


def test_live_groq_end_to_end(app, client):
    from app import create_app  # noqa: F401

    app.config["GROQ_API_KEY"] = _REAL_KEY
    app.extensions["docwiz"]._rag = None  # rebuild RAG with the key
    app.extensions["docwiz"].config = app.config
    app.extensions["docwiz"]._rag = None

    pdf = make_pdf(
        [
            "The mitochondrion is the organelle responsible for producing most of the cell's ATP "
            "through oxidative phosphorylation. It has its own circular DNA, supporting the "
            "endosymbiotic theory of eukaryotic cell evolution.",
        ]
        * 4
    )
    upload = client.post(
        "/api/documents",
        data={"files": (io.BytesIO(pdf), "Cell Biology.pdf")},
        content_type="multipart/form-data",
    )
    assert upload.status_code == 200

    response = client.post("/api/chat", json={"question": "Which organelle produces most ATP?"})
    assert response.status_code == 200
    body = response.get_json()
    assert body["grounded"] is True
    assert "mitochondrion" in body["answer"].lower() or "mitochondri" in body["answer"].lower()
    assert body["sources"], "live answer must include sources"
    assert body["sources"][0]["filename"] == "Cell Biology.pdf"
