"""Tests for the pluggable embedding layer (all HTTP mocked, no network).

Covers: provider config validation, request shaping for the Gemini and
OpenAI-compatible backends, retry/rate-limit handling, the disk cache,
and the vector store's embedding-identity guard.
"""
import numpy as np
import pytest

from app.services import embedding_service as es
from app.services.vector_store import VectorStore
from app.utils.errors import AppError


# ── helpers ───────────────────────────────────────────────────────────────

class FakeResponse:
    def __init__(self, status=200, body=None, headers=None, text=""):
        self.status_code = status
        self._body = body or {}
        self.headers = headers or {}
        self.text = text or str(self._body)

    def json(self):
        return self._body


def _gemini_body(n, dims):
    return {"embeddings": [{"values": [1.0] * dims} for _ in range(n)]}


# ── config validation ─────────────────────────────────────────────────────

def test_unknown_provider_rejected():
    with pytest.raises(AppError) as err:
        es.validate_embedding_config({"EMBEDDING_PROVIDER": "wat"})
    assert err.value.code == "embedding_provider_unknown"


def test_openai_compatible_requires_base_and_model():
    with pytest.raises(AppError) as err:
        es.validate_embedding_config({"EMBEDDING_PROVIDER": "openai-compatible"})
    assert err.value.code == "embedding_config_invalid"


def test_valid_gemini_config_passes():
    es.validate_embedding_config({"EMBEDDING_PROVIDER": "gemini"})  # no raise


# ── hashing backend (offline) ─────────────────────────────────────────────

def test_hashing_backend_is_deterministic_and_normalized():
    backend = es._HashingBackend(256)
    a = backend.embed(["TCP congestion control grows the window"])
    b = backend.embed(["TCP congestion control grows the window"])
    assert np.allclose(a, b)
    assert a.shape == (1, 256)
    assert np.isclose(np.linalg.norm(a[0]), 1.0)


def test_hashing_backend_scores_lexical_overlap():
    backend = es._HashingBackend(256)
    docs = backend.embed(
        [
            "TCP congestion control uses slow start and congestion avoidance",
            "Database normalization removes redundant attributes",
        ]
    )
    query = backend.embed(["How does TCP congestion control work?"])
    scores = docs @ query.T
    assert scores[0] > scores[1]  # TCP text matches the TCP query better


# ── Gemini backend (HTTP mocked) ──────────────────────────────────────────

def _patch_requests(monkeypatch, responder):
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen["url"], seen["json"], seen["headers"], seen["timeout"] = url, json, headers, timeout
        return responder(seen)

    monkeypatch.setattr(es.requests, "post", fake_post)
    return seen


def test_gemini_request_shape(monkeypatch):
    seen = _patch_requests(
        monkeypatch, lambda s: FakeResponse(200, _gemini_body(2, 768))
    )
    backend = es._GeminiBackend(
        "key-123", "gemini-embedding-001",
        "https://generativelanguage.googleapis.com/v1beta",
        768, "RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY", 30, 0,
    )
    vectors = backend.embed(["hello world", "second text"], task_type="RETRIEVAL_DOCUMENT")
    assert vectors.shape == (2, 768)
    assert seen["url"].endswith("/models/gemini-embedding-001:batchEmbedContents")
    assert seen["headers"]["x-goog-api-key"] == "key-123"
    request = seen["json"]["requests"][0]
    assert request["model"] == "models/gemini-embedding-001"
    assert request["content"]["parts"][0]["text"] == "hello world"
    assert request["task_type"] == "RETRIEVAL_DOCUMENT"
    assert request["output_dimensionality"] == 768
    assert len(seen["json"]["requests"]) == 2


def test_gemini_batches_large_document_sets(monkeypatch):
    calls = {"n": 0}

    def respond(seen):
        calls["n"] += 1
        n = len(seen["json"]["requests"])
        return FakeResponse(200, _gemini_body(n, 768))

    _patch_requests(monkeypatch, respond)
    backend = es._GeminiBackend("k", "gemini-embedding-001", "", 768, "", "", 30, 0)
    vectors = backend.embed([f"text {i}" for i in range(150)])
    assert calls["n"] == 3  # 64 + 64 + 22
    assert vectors.shape == (150, 768)


def test_gemini_retries_then_maps_rate_limit(monkeypatch):
    attempts = {"n": 0}
    sleeps = []

    def respond(_seen):
        attempts["n"] += 1
        return FakeResponse(429, {"error": {"message": "quota"}}, headers={"Retry-After": "3"})

    _patch_requests(monkeypatch, respond)
    monkeypatch.setattr(es.time, "sleep", lambda s: sleeps.append(s))
    backend = es._GeminiBackend("k", "gemini-embedding-001", "", 768, "", "", 30, 2)
    with pytest.raises(AppError) as err:
        backend.embed(["text"])
    assert err.value.code == "embedding_rate_limited"
    assert attempts["n"] == 3  # 1 + 2 retries
    assert "3" in err.value.message


def test_gemini_auth_error_mapping(monkeypatch):
    _patch_requests(monkeypatch, lambda s: FakeResponse(401, {"error": {"message": "bad key"}}))
    backend = es._GeminiBackend("k", "gemini-embedding-001", "", 768, "", "", 30, 0)
    with pytest.raises(AppError) as err:
        backend.embed(["text"])
    assert err.value.code == "embedding_auth_failed"


def test_gemini_bad_request_mapping(monkeypatch):
    _patch_requests(
        monkeypatch, lambda s: FakeResponse(400, {"error": {"message": "unsupported field"}})
    )
    backend = es._GeminiBackend("k", "gemini-embedding-001", "", 768, "", "", 30, 0)
    with pytest.raises(AppError) as err:
        backend.embed(["text"])
    assert err.value.code == "embedding_bad_request"
    assert "unsupported field" in err.value.message


# ── OpenAI-compatible backend ─────────────────────────────────────────────

def test_openai_compat_shape_and_index_order(monkeypatch):
    seen = _patch_requests(
        monkeypatch,
        lambda s: FakeResponse(
            200,
            {
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ]
            },
        ),
    )
    backend = es._OpenAICompatBackend("secret", "jina-embeddings-v3", "https://api.jina.ai/v1", 30, 0)
    vectors = backend.embed(["first", "second"])
    assert seen["url"] == "https://api.jina.ai/v1/embeddings"
    assert seen["headers"]["Authorization"] == "Bearer secret"
    assert seen["json"] == {"model": "jina-embeddings-v3", "input": ["first", "second"]}
    assert np.allclose(vectors[0], [1.0, 0.0])  # reordered by index


# ── EmbeddingService facade + cache ───────────────────────────────────────

def _service(tmp_path, backend, cache=True):
    return es.EmbeddingService(
        provider="test",
        backend=backend,
        model="test-model",
        embedding_id="test:test-model:d4",
        cache_path=tmp_path / "cache.npz",
        cache_enabled=cache,
    )


def test_service_cache_prevents_second_backend_call(tmp_path):
    calls = {"n": 0}

    class CountingBackend:
        ready = True

        def embed(self, texts, task_type=None):
            calls["n"] += 1
            return np.ones((len(texts), 4), dtype=np.float32)

    service = _service(tmp_path, CountingBackend())
    service.embed_documents(["a", "b"])
    service.embed_documents(["a", "b"])  # same texts → served from cache
    service.embed_query("a")
    assert calls["n"] == 2  # first doc call + query (different task key)


def test_service_cache_survives_restart(tmp_path):
    class StaticBackend:
        ready = True

        def embed(self, texts, task_type=None):
            return np.full((len(texts), 4), 0.5, dtype=np.float32)

    first = _service(tmp_path, StaticBackend())
    first.embed_documents(["persist me"])
    second = _service(tmp_path, StaticBackend())  # fresh instance, same file
    vectors = second.embed_documents(["persist me"])
    assert vectors.shape == (1, 4)


def test_service_normalizes_vectors(tmp_path):
    class RawBackend:
        ready = True

        def embed(self, texts, task_type=None):
            return np.array([[3.0, 0.0, 0.0, 0.0]] * len(texts), dtype=np.float32)

    service = _service(tmp_path, RawBackend(), cache=False)
    vectors = service.embed_documents(["x"])
    assert np.isclose(np.linalg.norm(vectors[0]), 1.0)


# ── vector store identity guard ───────────────────────────────────────────

def _chunks(n, doc_id="d1"):
    return [
        {"doc_id": doc_id, "chunk_id": f"{doc_id}-c{i:04d}", "text": f"t{i}", "page_start": 1, "page_end": 1}
        for i in range(n)
    ]


def test_store_records_embedding_identity(tmp_path):
    store = VectorStore(tmp_path / "index")
    store.add_document({"doc_id": "d1"}, _chunks(2), np.ones((2, 4), dtype=np.float32), embedding_id="prov-a:model:4")
    assert store.embedding_meta["embedding_id"] == "prov-a:model:4"
    # same id is fine on write and read
    store.add_document({"doc_id": "d2"}, _chunks(1, "d2"), np.ones((1, 4), dtype=np.float32), embedding_id="prov-a:model:4")
    store.search(np.ones((1, 4), dtype=np.float32), top_k=2, min_similarity=-1.0, embedding_id="prov-a:model:4")


def test_store_blocks_mixed_embedding_models(tmp_path):
    store = VectorStore(tmp_path / "index")
    store.add_document({"doc_id": "d1"}, _chunks(2), np.ones((2, 4), dtype=np.float32), embedding_id="prov-a:model:4")
    with pytest.raises(AppError) as err:
        store.add_document({"doc_id": "d2"}, _chunks(1, "d2"), np.ones((1, 8), dtype=np.float32), embedding_id="prov-b:model:8")
    assert err.value.code == "embedding_model_changed"
    with pytest.raises(AppError) as err:
        store.search(np.ones((1, 4), dtype=np.float32), top_k=2, min_similarity=-1.0, embedding_id="prov-b:model:4")
    assert err.value.code == "embedding_model_changed"
    assert "prov-b:model:4" in err.value.message  # names both sides of the clash


def test_store_allows_provider_switch_on_empty_library(tmp_path):
    store = VectorStore(tmp_path / "index")
    store.add_document({"doc_id": "d1"}, _chunks(2), np.ones((2, 4), dtype=np.float32), embedding_id="prov-a:model:4")
    store.remove_document("d1")
    # library is now empty — switching providers must not be blocked
    store.add_document({"doc_id": "d2"}, _chunks(1, "d2"), np.ones((1, 8), dtype=np.float32), embedding_id="prov-b:model:8")
    assert store.embedding_meta["embedding_id"] == "prov-b:model:8"


def test_store_treats_legacy_index_as_incompatible(tmp_path):
    # Simulate an index written by an older DocWiz (no index_meta.json)
    import json

    index_dir = tmp_path / "index"
    index_dir.mkdir()
    (index_dir / "documents.json").write_text(json.dumps({"d1": {"doc_id": "d1"}}), encoding="utf-8")
    (index_dir / "chunks.json").write_text(json.dumps(_chunks(1)), encoding="utf-8")
    np.savez_compressed(index_dir / "vectors.npz", vectors=np.ones((1, 384), dtype=np.float32))

    store = VectorStore(index_dir)
    with pytest.raises(AppError) as err:
        store.search(np.ones((1, 768), dtype=np.float32), top_k=1, min_similarity=-1.0, embedding_id="gemini:gemini-embedding-001:d768")
    assert err.value.code == "embedding_model_changed"
    assert "older DocWiz" in err.value.message


def test_store_identity_persists_across_restart(tmp_path):
    store = VectorStore(tmp_path / "index")
    store.add_document({"doc_id": "d1"}, _chunks(2), np.ones((2, 4), dtype=np.float32), embedding_id="prov-a:model:4")
    reopened = VectorStore(tmp_path / "index")
    assert reopened.embedding_meta["embedding_id"] == "prov-a:model:4"


# ── factory ───────────────────────────────────────────────────────────────

def test_factory_builds_gemini_service_with_defaults():
    service = es.build_embedding_service({"EMBEDDING_PROVIDER": "gemini", "DATA_DIR": None})
    assert service.provider == "gemini"
    assert service.model == "gemini-embedding-001"
    assert service.embedding_id == "gemini:gemini-embedding-001:d768"
    assert service.loaded is False  # no key configured


def test_factory_groq_preset_shares_groq_key():
    service = es.build_embedding_service(
        {"EMBEDDING_PROVIDER": "groq", "GROQ_API_KEY": "g-key", "DATA_DIR": None}
    )
    assert service.model == "nomic-embed-text-v1_5"
    assert service.loaded is True  # key inherited from GROQ_API_KEY
