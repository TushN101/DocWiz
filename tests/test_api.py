"""API-level tests using the Flask test client.

Upload tests use the built-in offline `hashing` embedder (see conftest),
so the whole suite runs without network, API keys, or model downloads.
The live Groq test skips itself without a key.
"""
import io
import os

import pytest

from tests.conftest import make_pdf


def _upload(client, data, filename, unique_name=None):
    name = unique_name or filename
    return client.post(
        "/api/documents",
        data={"files": (io.BytesIO(data), name)},
        content_type="multipart/form-data",
    )


class TestHealth:
    def test_health_reports_status(self, client):
        body = client.get("/api/health").get_json()
        assert body["status"] == "ok"
        assert body["api_key_configured"] is False  # tests run without a key
        assert body["documents"] == 0


class TestUpload:
    def test_upload_rejects_non_pdf(self, client):
        response = _upload(client, b"plain text", "notes.txt")
        body = response.get_json()
        assert response.status_code == 400
        assert body["results"][0]["ok"] is False
        assert body["results"][0]["error"]["code"] == "invalid_file_type"

    def test_upload_rejects_renamed_file(self, client):
        response = _upload(client, b"this is not a pdf", "fake.pdf")
        body = response.get_json()
        assert body["results"][0]["error"]["code"] == "not_a_real_pdf"

    def test_upload_no_files(self, client):
        response = client.post("/api/documents", data={}, content_type="multipart/form-data")
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "no_files"

    def test_upload_scanned_pdf_is_rejected(self, client, unique_name):
        scanned = make_pdf(["", ""], scanned=True)
        response = _upload(client, scanned, unique_name)
        body = response.get_json()
        assert body["results"][0]["error"]["code"] == "no_extractable_text"

    def test_upload_and_index_pdf(self, client, sample_two_page_pdf, unique_name):
        response = _upload(client, sample_two_page_pdf, unique_name)
        body = response.get_json()
        assert response.status_code == 200
        result = body["results"][0]
        assert result["ok"] is True
        assert result["pages"] == 2
        assert result["chunks"] >= 1

        listing = client.get("/api/documents").get_json()
        assert len(listing["documents"]) == 1
        doc = listing["documents"][0]
        assert doc["filename"] == unique_name
        assert doc["pages"] == 2


class TestDeleteAndReset:
    def test_delete_document(self, client, sample_two_page_pdf, unique_name):
        upload = _upload(client, sample_two_page_pdf, unique_name).get_json()
        doc_id = next(r["doc_id"] for r in upload["results"] if r["ok"])

        response = client.delete(f"/api/documents/{doc_id}")
        assert response.status_code == 200
        assert client.get("/api/documents").get_json()["documents"] == []

    def test_delete_unknown_document(self, client):
        response = client.delete("/api/documents/doesnotexist")
        assert response.status_code == 404


class TestChat:
    def test_empty_question_rejected(self, client):
        response = client.post("/api/chat", json={"question": "   "})
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "empty_question"

    def test_missing_body_rejected(self, client):
        response = client.post("/api/chat", json={})
        assert response.status_code == 400

    def test_chat_without_documents(self, client):
        response = client.post("/api/chat", json={"question": "What is TCP congestion control?"})
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "no_documents"

    def test_chat_with_documents_but_no_api_key(self, client, sample_two_page_pdf, unique_name):
        _upload(client, sample_two_page_pdf, unique_name)
        response = client.post("/api/chat", json={"question": "What is photosynthesis?"})
        assert response.status_code == 503
        body = response.get_json()
        assert body["error"]["code"] == "api_key_missing"
        assert ".env" in body["error"]["message"]  # points the user at the fix

    def test_reset_clears_library(self, client, sample_two_page_pdf, unique_name):
        _upload(client, sample_two_page_pdf, unique_name)
        assert client.post("/api/reset").status_code == 200
        assert client.get("/api/documents").get_json()["documents"] == []


class TestFrontendServed:
    def test_index_page_served(self, client):
        response = client.get("/")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "DocWiz" in html
        assert "style.css" in html

    def test_unknown_api_route_is_json_404(self, client):
        response = client.get("/api/does-not-exist")
        assert response.status_code == 404
        assert response.get_json()["error"]["code"] == "not_found"


class TestRetrievalQuality:
    """The TCP question should retrieve from Computer Networks.pdf, not the DBMS book."""

    def test_relevant_document_wins(self, client):
        from app.utils.text import sanitize_filename

        networks_name = sanitize_filename("Computer Networks.pdf")  # "Computer_Networks.pdf"
        networks = make_pdf(
            ["TCP congestion control uses slow start and congestion avoidance. "
             "The congestion window grows exponentially during slow start. "
             "Fast retransmit and fast recovery handle packet loss gracefully."] * 6
        )
        dbms = make_pdf(
            ["Database normalization removes redundancy. "
             "Third normal form eliminates transitive dependencies between attributes. "
             "Indexes accelerate query processing in relational database systems."] * 6
        )
        response = client.post(
            "/api/documents",
            data={
                "files": [
                    (io.BytesIO(networks), "Computer Networks.pdf"),
                    (io.BytesIO(dbms), "Database Systems.pdf"),
                ]
            },
            content_type="multipart/form-data",
        )
        assert response.status_code == 200

        # Retrieval is exercised through the shared service container
        # (chat itself would stop at the missing-key guard).
        svc = client.application.extensions["docwiz"]
        query_vector = svc.embedder.embed_query("How does TCP congestion control work?")
        hits = svc.store.search(query_vector, top_k=5, min_similarity=0.2)
        assert hits, "expected at least one hit"
        top_docs = {h["chunk"]["doc_id"] for h in hits[:3]}
        nets_id = next(
            d["doc_id"] for d in svc.store.list_documents() if d["filename"] == networks_name
        )
        assert nets_id in top_docs, "Computer Networks.pdf should dominate retrieval"
        best = hits[0]["chunk"]
        assert "congestion" in best["text"].lower()
