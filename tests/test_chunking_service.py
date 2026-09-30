"""Tests for page-aware chunking (no network, no model)."""
from app.services.chunking_service import chunk_pages


def _pages(*texts):
    return [{"page": i + 1, "text": t} for i, t in enumerate(texts)]


def test_basic_chunking_produces_chunks_with_metadata():
    long_text = (
        "TCP congestion control prevents network collapse. " * 40
    )
    chunks = chunk_pages(_pages(long_text), doc_id="abc123")
    assert len(chunks) >= 2
    for i, chunk in enumerate(chunks):
        assert chunk["doc_id"] == "abc123"
        assert chunk["chunk_id"] == f"abc123-c{i + 1:04d}"
        assert chunk["page_start"] == 1
        assert chunk["page_end"] == 1
        assert chunk["text"].strip() == chunk["text"]


def test_page_numbers_follow_content_across_pages():
    p1 = "Operating systems manage hardware resources. " * 30
    p2 = "Databases store structured information. " * 30
    chunks = chunk_pages(_pages(p1, p2), doc_id="d1")
    assert any(c["page_start"] == 1 for c in chunks)
    assert any(c["page_start"] == 2 for c in chunks)
    # chunks are ordered and never span backwards
    pages_seen = [c["page_start"] for c in chunks]
    assert pages_seen == sorted(pages_seen)


def test_overlap_carries_text_between_chunks():
    text = "Sentence number {} explains retrieval augmented generation pipelines. " * 1
    long_text = " ".join(f"Sentence {i} explains the retrieval augmented generation pipeline flow." for i in range(60))
    chunks = chunk_pages(_pages(long_text), doc_id="d2", chunk_size=400, overlap=120)
    assert len(chunks) >= 3
    # consecutive chunks should share some words thanks to the overlap
    tail_last_words = chunks[0]["text"].split()[-8:]
    head_next_words = chunks[1]["text"].split()[:8]
    assert set(map(str.lower, tail_last_words)) & set(map(str.lower, head_next_words))


def test_short_document_single_chunk():
    chunks = chunk_pages(_pages("A short document."), doc_id="d3")
    assert len(chunks) == 1
    assert chunks[0]["text"] == "A short document."


def test_tiny_trailing_chunk_is_merged():
    text = "Filler sentence one. " * 80 + "End."
    chunks = chunk_pages(_pages(text), doc_id="d4", chunk_size=500, overlap=60)
    assert len(chunks) >= 2
    assert len(chunks[-1]["text"]) >= 20  # no 4-char orphan tail


def test_empty_pages_list_returns_no_chunks():
    assert chunk_pages([], doc_id="d5") == []
    assert chunk_pages(_pages("", ""), doc_id="d6") == []


def test_chunks_carry_filename_metadata():
    """Regression: the LLM context builder reads chunk['filename'] — the
    chunker must stamp it so source attribution survives retrieval."""
    chunks = chunk_pages(_pages("Chunker test text."), doc_id="d7", filename="My Report.pdf")
    assert len(chunks) == 1
    assert chunks[0]["filename"] == "My Report.pdf"
    # canonical schema: exactly the agreed keys, nothing less
    assert set(chunks[0]) == {"doc_id", "chunk_id", "filename", "text", "page_start", "page_end"}
