"""Tests for the NumPy vector store: add / search / remove / persistence.

Uses synthetic vectors — no embedding model or network required.
"""
import numpy as np
import pytest

from app.services.vector_store import VectorStore


def _vec(seed, dim=16):
    rng = np.random.default_rng(seed)
    v = rng.random((1, dim)).astype(np.float32)
    return v / np.linalg.norm(v)


def _chunk(doc_id, i, text):
    return {
        "doc_id": doc_id,
        "chunk_id": f"{doc_id}-c{i:04d}",
        "text": text,
        "page_start": 1,
        "page_end": 1,
    }


@pytest.fixture()
def store(tmp_path):
    return VectorStore(tmp_path / "index")


def test_add_and_stats(store):
    chunks = [_chunk("a", i, f"text {i}") for i in range(1, 4)]
    vectors = np.vstack([_vec(i) for i in range(3)]).astype(np.float32)
    store.add_document(
        {"doc_id": "a", "filename": "A.pdf", "uploaded_at": "t0"}, chunks, vectors
    )
    assert store.document_count == 1
    assert store.chunk_count == 3
    assert not store.is_empty()


def test_search_returns_best_match(store):
    target = _vec(42)
    chunks = [
        _chunk("a", 1, "target chunk"),
        _chunk("a", 2, "other chunk"),
        _chunk("a", 3, "filler one"),
        _chunk("a", 4, "filler two"),
        _chunk("a", 5, "filler three"),
    ]
    rng = np.random.default_rng(0)
    others = rng.random((4, 16)).astype(np.float32)
    others /= np.linalg.norm(others, axis=1, keepdims=True)
    vectors = np.vstack([target, others])  # target is row 0
    store.add_document({"doc_id": "a", "filename": "A.pdf", "uploaded_at": "t0"}, chunks, vectors)

    hits = store.search(target.reshape(1, -1), top_k=2, min_similarity=-1.0)
    assert hits[0]["chunk"]["text"] == "target chunk"


def test_similarity_threshold_filters(store):
    rng = np.random.default_rng(1)
    vectors = rng.random((3, 16)).astype(np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    chunks = [_chunk("a", i, f"c{i}") for i in range(3)]
    store.add_document({"doc_id": "a", "filename": "A.pdf", "uploaded_at": "t0"}, chunks, vectors)

    unrelated = _vec(999)
    hits = store.search(unrelated.reshape(1, -1), top_k=3, min_similarity=0.99)
    assert hits == []  # random vectors won't be that similar


def test_remove_document_drops_only_its_chunks(store):
    chunks_a = [_chunk("a", 1, "a1"), _chunk("a", 2, "a2")]
    chunks_b = [_chunk("b", 1, "b1")]
    store.add_document(
        {"doc_id": "a", "filename": "A.pdf", "uploaded_at": "t0"},
        chunks_a,
        np.vstack([_vec(1), _vec(2)]),
    )
    store.add_document(
        {"doc_id": "b", "filename": "B.pdf", "uploaded_at": "t1"},
        chunks_b,
        _vec(3),
    )
    assert store.remove_document("a") is True
    assert store.remove_document("a") is False
    assert store.chunk_count == 1
    assert store._chunks[0]["text"] == "b1"
    assert store._vectors.shape == (1, 16)


def test_persistence_roundtrip(tmp_path):
    index_dir = tmp_path / "index"
    store1 = VectorStore(index_dir)
    chunks = [_chunk("a", 1, "persistent chunk")]
    store1.add_document(
        {"doc_id": "a", "filename": "A.pdf", "uploaded_at": "t0"},
        chunks,
        _vec(7),
    )

    store2 = VectorStore(index_dir)  # simulates a server restart
    assert store2.document_count == 1
    assert store2.chunk_count == 1
    assert store2._chunks[0]["text"] == "persistent chunk"
    hits = store2.search(_vec(7), top_k=1, min_similarity=0.9)
    assert len(hits) == 1


def test_dimension_mismatch_is_flagged(store):
    store.add_document(
        {"doc_id": "a", "filename": "A.pdf", "uploaded_at": "t0"},
        [_chunk("a", 1, "x")],
        _vec(1, dim=16),
    )
    from app.utils.errors import AppError

    with pytest.raises(AppError):
        store.add_document(
            {"doc_id": "b", "filename": "B.pdf", "uploaded_at": "t1"},
            [_chunk("b", 1, "y")],
            _vec(2, dim=8),
        )


# ── canonical chunk metadata (filename must survive the pipeline) ──────────

def test_add_document_backfills_missing_filename(store):
    legacy = {"doc_id": "a", "chunk_id": "a-c0001", "text": "legacy chunk", "page_start": 2, "page_end": 2}
    store.add_document({"doc_id": "a", "filename": "Report.pdf", "uploaded_at": "t0"}, [legacy], _vec(1))
    hits = store.search(_vec(1), top_k=1, min_similarity=-1.0)
    assert hits[0]["chunk"]["filename"] == "Report.pdf"


def test_add_document_normalizes_unusual_page_metadata(store):
    weird = {"doc_id": "a", "chunk_id": "a-c0001", "filename": "A.pdf", "text": "odd pages", "page_start": "3", "page_end": None}
    store.add_document({"doc_id": "a", "filename": "A.pdf", "uploaded_at": "t0"}, [weird], _vec(5))
    hits = store.search(_vec(5), top_k=1, min_similarity=-1.0)
    chunk = hits[0]["chunk"]
    assert chunk["page_start"] == 3 and chunk["page_end"] == 3  # coerced, end >= start


def test_legacy_index_without_filename_is_migrated_on_load(tmp_path):
    """Indexes written before the canonical schema must not produce malformed
    retrieval results: filenames are backfilled from documents.json on load."""
    index_dir = tmp_path / "index"
    store1 = VectorStore(index_dir)
    store1.add_document(
        {"doc_id": "a", "filename": "Thesis.pdf", "uploaded_at": "t0"},
        [_chunk("a", 1, "legacy persisted chunk")],
        _vec(11),
    )
    # Simulate the old on-disk schema by stripping the filename field.
    import json

    chunks_path = index_dir / "chunks.json"
    legacy_chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    for c in legacy_chunks:
        c.pop("filename", None)
    chunks_path.write_text(json.dumps(legacy_chunks), encoding="utf-8")

    store2 = VectorStore(index_dir)  # reload triggers the migration
    hits = store2.search(_vec(11), top_k=1, min_similarity=-1.0)
    assert hits[0]["chunk"]["filename"] == "Thesis.pdf"
    # And the migration is persisted, so it does not re-run afterwards.
    on_disk = json.loads(chunks_path.read_text(encoding="utf-8"))
    assert on_disk[0]["filename"] == "Thesis.pdf"


def test_unrecoverable_chunk_rows_are_dropped_and_vectors_realigned(tmp_path):
    import json

    index_dir = tmp_path / "index"
    store1 = VectorStore(index_dir)
    store1.add_document(
        {"doc_id": "a", "filename": "A.pdf", "uploaded_at": "t0"},
        [_chunk("a", 1, "good one"), _chunk("a", 2, "good two")],
        np.vstack([_vec(21), _vec(22)]),
    )
    chunks_path = index_dir / "chunks.json"
    legacy = json.loads(chunks_path.read_text(encoding="utf-8"))
    legacy.append({"chunk_id": "orphan", "text": "no doc id here"})  # malformed row
    chunks_path.write_text(json.dumps(legacy), encoding="utf-8")

    store2 = VectorStore(index_dir)
    assert store2.chunk_count == 2  # malformed row dropped
    assert store2._vectors.shape == (2, 16)  # vectors stayed aligned with chunks
    hits = store2.search(_vec(22), top_k=2, min_similarity=-1.0)
    assert any(h["chunk"]["text"] == "good two" for h in hits)
