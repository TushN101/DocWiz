"""Page-aware chunking.

Strategy (see research.md §B):
  * per-page texts are joined with page-offset bookkeeping,
  * a sliding window (chunk_size / overlap) walks the combined text,
  * cut points snap to the last sentence boundary inside the window,
  * every chunk records the page(s) it spans via a bisect over page ranges,
  * trailing mini-chunks are merged into the previous chunk.
"""
import bisect
import re

_SENTENCE_END = re.compile(r"[.!?…][\"')\]]?(\s+|$)")


def _build_page_index(pages):
    """Join page texts; return (combined_text, page_starts, page_of_offset helper data)."""
    parts, page_starts = [], []
    offset = 0
    for entry in pages:
        text = entry["text"]
        if not text:
            continue
        page_starts.append(offset)
        parts.append(text)
        offset += len(text) + 2  # 2 chars for the "\n\n" separator
    combined = "\n\n".join(parts)
    return combined, page_starts


def _page_for_offset(offset: int, page_starts, page_numbers):
    idx = bisect.bisect_right(page_starts, offset) - 1
    idx = max(0, min(idx, len(page_numbers) - 1))
    return page_numbers[idx]


def _find_cut(text: str, window_end: int, min_cut: int) -> int:
    """Prefer the last sentence end at/before window_end; otherwise hard cut."""
    region = text[min_cut:window_end]
    last = -1
    for match in _SENTENCE_END.finditer(region):
        last = match.start() + len(match.group(1)) if match.group(1) else match.end()
    if last >= 0:
        return min_cut + last
    # fall back to a word boundary so we never split mid-word
    snippet = text[min_cut:window_end]
    space = snippet.rfind(" ")
    if space > 0:
        return min_cut + space + 1
    return window_end


def _next_start(text: str, cut: int, overlap: int) -> int:
    start = max(cut - overlap, 0)
    if start > 0:
        space = text.find(" ", start)
        if space != -1 and space < cut:
            start = space + 1
    return start


def chunk_pages(
    pages,
    doc_id: str,
    chunk_size: int = 1100,
    overlap: int = 180,
    min_chunk_chars: int = 80,
    filename: str = "",
):
    """Convert per-page texts into metadata-carrying chunks.

    Canonical chunk schema (must stay identical from chunker → vector store →
    retrieval → LLM context builder):

      {"doc_id", "chunk_id", "filename", "text", "page_start", "page_end"}

    `filename` is the display name of the source document. It is stamped onto
    every chunk here so that the LLM layer can attribute context passages
    without a registry lookup, and so source attribution survives the entire
    retrieval pipeline (vector_store additionally guards this on write/load).
    """
    combined, page_starts = _build_page_index(pages)
    page_numbers = [entry["page"] for entry in pages if entry["text"]]
    if not combined.strip():
        return []

    spans = []
    start = 0
    min_cut = max(chunk_size // 2, 1)
    guard = 0
    while start < len(combined) and guard < 10000:
        guard += 1
        window_end = min(start + chunk_size, len(combined))
        cut = _find_cut(combined, window_end, min_cut) if window_end < len(combined) else window_end
        if cut <= start:
            cut = window_end
        spans.append((start, cut))
        if cut >= len(combined):
            break
        start = _next_start(combined, cut, overlap)
        if start <= spans[-1][0]:
            start = cut

    chunks = []
    for i, (s, e) in enumerate(spans):
        text = combined[s:e].strip()
        if not text:
            continue
        page_start = _page_for_offset(s, page_starts, page_numbers)
        page_end = _page_for_offset(max(e - 1, s), page_starts, page_numbers)
        chunks.append(
            {
                "doc_id": doc_id,
                "chunk_id": f"{doc_id}-c{i + 1:04d}",
                "filename": str(filename or ""),
                "text": text,
                "page_start": page_start,
                "page_end": page_end,
            }
        )

    # merge a trailing mini-chunk into its predecessor
    if len(chunks) > 1 and len(chunks[-1]["text"]) < min_chunk_chars:
        tail = chunks.pop()
        prev = chunks[-1]
        prev["text"] = prev["text"] + " " + tail["text"]
        prev["page_end"] = max(prev["page_end"], tail["page_end"])

    return chunks
