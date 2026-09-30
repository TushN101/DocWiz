"""Tests for the RAG orchestration and LLM service (fully mocked, no network)."""
import numpy as np
import pytest

from app.services import llm_service
from app.services.rag_service import RagService
from app.utils.errors import AppError


class FakeEmbedder:
    def embed_query(self, question):
        return np.ones((1, 4), dtype=np.float32) / 2

    def embed_documents(self, texts):
        return np.ones((len(texts), 4), dtype=np.float32) / 2


class FakeStore:
    def __init__(self, hits=None, empty=False):
        self._hits = hits or []
        self._empty = empty

    def is_empty(self):
        return self._empty

    def search(self, *_args, **_kwargs):
        return self._hits

    def filename_for(self, doc_id):
        return "Networks.pdf" if doc_id == "n1" else "Unknown document"


def _hit(text="TCP uses congestion windows to avoid collapse.", doc_id="n1", page=142, score=0.72):
    return {
        "chunk": {
            "doc_id": doc_id,
            "chunk_id": f"{doc_id}-c0001",
            "text": text,
            "page_start": page,
            "page_end": page,
            "filename": "Networks.pdf",
        },
        "score": score,
    }


class _RagConfig:
    GROQ_API_KEY = "test-key"
    GROQ_API_URL = "http://localhost:1"
    GROQ_MODEL = "openai/gpt-oss-120b"
    GROQ_TEMPERATURE = 0.2
    GROQ_TOP_P = 0.9
    GROQ_MAX_COMPLETION_TOKENS = 128
    GROQ_TIMEOUT_SECONDS = 5
    TOP_K = 5
    MIN_SIMILARITY = 0.2
    NEAR_DUPLICATE_CUTOFF = 0.95
    MAX_CONTEXT_CHARS = 12000
    MAX_CHUNK_CHARS_IN_CONTEXT = 2600
    MAX_QUESTION_CHARS = 2000
    EXCERPT_CHARS = 240


# ── RAG service ───────────────────────────────────────────────────────────

def test_rag_rejects_empty_question():
    rag = RagService(FakeEmbedder(), FakeStore(), _RagConfig())
    with pytest.raises(AppError) as err:
        rag.answer("   ")
    assert err.value.code == "empty_question"


def test_rag_requires_documents():
    rag = RagService(FakeEmbedder(), FakeStore(empty=True), _RagConfig())
    with pytest.raises(AppError) as err:
        rag.answer("What is TCP?")
    assert err.value.code == "no_documents"


def test_rag_requires_api_key():
    config = _RagConfig()
    config.GROQ_API_KEY = ""
    rag = RagService(FakeEmbedder(), FakeStore(hits=[_hit()]), config)
    with pytest.raises(AppError) as err:
        rag.answer("What is TCP?")
    assert err.value.code == "api_key_missing"


def test_rag_honest_answer_when_nothing_retrieved(monkeypatch):
    # store returns no hits; the LLM must NOT be called
    called = {"n": 0}

    def boom(**_kwargs):
        called["n"] += 1
        raise AssertionError("LLM should not be called when nothing is retrieved")

    monkeypatch.setattr(llm_service, "answer_question", boom)
    rag = RagService(FakeEmbedder(), FakeStore(hits=[]), _RagConfig())
    result = rag.answer("What is quantum tunneling?")
    assert result["grounded"] is False
    assert result["sources"] == []
    assert "couldn't find" in result["answer"]
    assert called["n"] == 0


def test_rag_sources_map_to_retrieved_chunks(monkeypatch):
    monkeypatch.setattr(
        llm_service, "answer_question", lambda **_kw: "Congestion control avoids collapse."
    )
    rag = RagService(FakeEmbedder(), FakeStore(hits=[_hit(), _hit(page=143, score=0.6)]), _RagConfig())
    result = rag.answer("How does TCP avoid collapse?")
    assert result["grounded"] is True
    assert [s["page_start"] for s in result["sources"]] == [142, 143]
    assert all(s["filename"] == "Networks.pdf" for s in result["sources"])
    assert all("TCP uses congestion" in s["excerpt"] or s["excerpt"] for s in result["sources"])


# ── LLM service (HTTP mocked) ─────────────────────────────────────────────

class FakeResponse:
    def __init__(self, status=200, body=None, headers=None, text=""):
        self.status_code = status
        self._body = body or {}
        self.headers = headers or {}
        self.text = text or str(self._body)

    def json(self):
        return self._body


def _patch_post(monkeypatch, response):
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen["url"] = url
        seen["json"] = json
        seen["headers"] = headers
        return response

    monkeypatch.setattr(llm_service.requests, "post", fake_post)
    return seen


def _call_llm():
    return llm_service.answer_question(
        question="What is TCP slow start?",
        retrieved=[_hit()],
        api_key="secret-key",
        api_url="https://api.example.test/chat",
        model="openai/gpt-oss-120b",
        temperature=0.2,
        top_p=0.9,
        max_tokens=256,
        timeout=10,
    )


def test_llm_success_returns_content(monkeypatch):
    seen = _patch_post(
        monkeypatch,
        FakeResponse(200, {"choices": [{"message": {"content": " Slow start grows the window. "}}]}),
    )
    assert _call_llm() == "Slow start grows the window."
    assert seen["json"]["model"] == "openai/gpt-oss-120b"
    assert seen["headers"]["Authorization"] == "Bearer secret-key"
    context_blob = seen["json"]["messages"][1]["content"]
    assert "[1] Source:" in context_blob
    assert "page 142" in context_blob
    assert "Networks.pdf" in context_blob


def test_llm_auth_error_mapping(monkeypatch):
    _patch_post(monkeypatch, FakeResponse(401, {"error": {"message": "bad key"}}))
    with pytest.raises(AppError) as err:
        _call_llm()
    assert err.value.code == "llm_auth_failed"


def test_llm_rate_limit_mapping(monkeypatch):
    _patch_post(monkeypatch, FakeResponse(429, {}, headers={"Retry-After": "7"}))
    with pytest.raises(AppError) as err:
        _call_llm()
    assert err.value.code == "llm_rate_limited"
    assert "7" in err.value.message


def test_llm_model_missing_mapping(monkeypatch):
    _patch_post(monkeypatch, FakeResponse(404, {"error": {"message": "model not found"}}))
    with pytest.raises(AppError) as err:
        _call_llm()
    assert err.value.code == "llm_model_unavailable"


def test_llm_system_prompt_contains_grounding_rules(monkeypatch):
    seen = _patch_post(monkeypatch, FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]}))
    _call_llm()
    system = seen["json"]["messages"][0]["content"]
    assert "ONLY the context" in system
    assert "NEVER invent" in system
    assert "do not cover" in system or "does not cover" in system
