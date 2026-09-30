"""Small text / filename helpers shared across services."""
import re

from werkzeug.utils import secure_filename


def sanitize_filename(raw_name: str) -> str:
    """Return a filesystem-safe version of an uploaded filename.

    Falls back to a generic name when secure_filename strips everything
    (e.g. names made only of non-ASCII characters).
    """
    name = (raw_name or "").strip()
    safe = secure_filename(name)
    if not safe:
        safe = "document.pdf"
    if not safe.lower().endswith(".pdf"):
        safe += ".pdf"
    return safe


_WHITESPACE_RE = re.compile(r"[ \t]+")


def normalize_text(text: str) -> str:
    """Collapse runs of spaces/tabs (PDF extraction artifacts) but keep line structure."""
    lines = []
    for line in text.splitlines():
        line = _WHITESPACE_RE.sub(" ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def extract_excerpt(text: str, limit: int = 240) -> str:
    """Short verbatim excerpt from a chunk, cut at a word boundary.

    The excerpt is always taken from the retrieved chunk text itself,
    so fabricated quotations are impossible.
    """
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    cut = clean[:limit]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(",;:.") + "…"


def split_paragraphs(text: str):
    """Split an LLM answer into non-empty paragraphs."""
    paragraphs = []
    for block in re.split(r"\n\s*\n", text or ""):
        block = block.strip()
        if block:
            paragraphs.append(block)
    return paragraphs
