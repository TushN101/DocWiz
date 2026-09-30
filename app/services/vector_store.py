"""Lightweight local vector store: NumPy cosine index + JSON metadata.

Why not FAISS/Chroma? See research.md §D — at this project's scale
(≤ ~3,000 chunks) a brute-force matmul over a float32 matrix answers in
under 5 ms, with zero extra dependencies and trivial persistence.

Persistence layout (data/index/):
  documents.json  — registry: doc_id → metadata (filename, pages, counts…)
  chunks.json     — list of chunk dicts (text + source metadata)
  vectors.npz     — float32 matrix aligned with chunks.json order

Thread-safety: mutations take a lock and swap immutable references;
searches read the latest committed snapshot without blocking.
"""
import json
import logging
import threading

import numpy as np

from app.utils.errors import AppError

logger = logging.getLogger("docwiz.store")

DOCUMENTS_FILE = "documents.json"
CHUNKS_FILE = "chunks.json"
VECTORS_FILE = "vectors.npz"
INDEX_META_FILE = "index_meta.json"

LEGACY_EMBEDDING_ID = "legacy:unknown:unknown"

# Canonical chunk schema shared with chunking_service / rag_service / llm_service.
CANONICAL_CHUNK_KEYS = ("doc_id", "chunk_id", "filename", "text", "page_start", "page_end")
UNKNOWN_FILENAME = "Unknown document"


def _coerce_page(value) -> int:
    """Best-effort page number: sane, positive int; unusual values become 1."""
    try:
        page = int(value)
    except (TypeError, ValueError):
        return 1
    return page if page >= 1 else 1


def _normalize_chunk(chunk, doc_meta=None):
    """Return a chunk dict matching the canonical schema, or None if unrecoverable.

    The store accepts chunks produced by any DocWiz version and guarantees that
    everything it stores and returns carries the full canonical metadata:

      {"doc_id", "chunk_id", "filename", "text", "page_start", "page_end"}

    * `filename` missing/blank → taken from the document registry when
      available, else "Unknown document" (an unusual/legacy chunk must never
      crash retrieval or the LLM context builder).
    * pages are coerced to positive ints with page_end >= page_start.
    * chunks without a doc_id or usable text are unrecoverable → None (they
      could never be meaningfully retrieved).
    """
    if not isinstance(chunk, dict):
        return None
    doc_id = str(chunk.get("doc_id") or "").strip()
    text = chunk.get("text")
    if not doc_id or not isinstance(text, str) or not text.strip():
        return None

    filename = chunk.get("filename")
    if not isinstance(filename, str) or not filename.strip():
        filename = (doc_meta or {}).get("filename") if doc_meta else None
    if not isinstance(filename, str) or not filename.strip():
        filename = UNKNOWN_FILENAME

    page_start = _coerce_page(chunk.get("page_start"))
    page_end = max(page_start, _coerce_page(chunk.get("page_end")))
    chunk_id = str(chunk.get("chunk_id") or "").strip() or f"{doc_id}-c0000"

    return {
        "doc_id": doc_id,
        "chunk_id": chunk_id,
        "filename": filename.strip(),
        "text": text,
        "page_start": page_start,
        "page_end": page_end,
    }


class VectorStore:
    def __init__(self, index_dir):
        self.index_dir = index_dir
        self._lock = threading.Lock()
        self._documents = {}  # doc_id -> metadata dict
        self._chunks = []     # list of chunk dicts
        self._vectors = None  # np.ndarray (n, dim) float32
        self._embedding_meta = None  # {"embedding_id", "dims"} of the index
        self._load()

    @property
    def embedding_meta(self):
        return dict(self._embedding_meta) if self._embedding_meta else None

    # ------------------------------------------------------------------ state
    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    @property
    def document_count(self) -> int:
        return len(self._documents)

    def is_empty(self) -> bool:
        return len(self._chunks) == 0

    def list_documents(self):
        with self._lock:
            return sorted(self._documents.values(), key=lambda d: d["uploaded_at"])

    def get_document(self, doc_id):
        return self._documents.get(doc_id)

    def filename_for(self, doc_id):
        doc = self._documents.get(doc_id)
        return doc["filename"] if doc else "Unknown document"

    # ------------------------------------------------------------------ mutate
    def add_document(self, doc_meta, chunks, vectors, embedding_id=None):
        """Register a document, its chunks and their vectors; persist to disk.

        `embedding_id` identifies the provider/model that produced the
        vectors (e.g. "gemini:gemini-embedding-001:d768"). If the index was
        built with a different model, the write is refused: vector spaces
        from different embedding models are not comparable.
        """
        if len(chunks) != len(vectors):
            raise AppError("index_failure", "Chunk/vector count mismatch while indexing.", 500)
        doc_id = doc_meta["doc_id"]
        normalized = []
        for chunk in chunks:
            clean = _normalize_chunk(chunk, doc_meta)
            if clean is None:
                raise AppError(
                    "index_failure",
                    "A chunk was missing required metadata while indexing. Please retry the upload.",
                    500,
                )
            normalized.append(clean)
        with self._lock:
            self._check_embedding_identity(embedding_id, vectors_shape=vectors.shape)
            if self._vectors is not None and self._vectors.size:
                dim = self._vectors.shape[1]
                if vectors.shape[1] != dim:
                    raise AppError(
                        "index_failure",
                        "Embedding dimension mismatch with the existing index. Clear the library to re-index.",
                        500,
                    )
                new_matrix = np.vstack([self._vectors, vectors])
            else:
                new_matrix = np.asarray(vectors, dtype=np.float32)
            self._documents[doc_id] = doc_meta
            self._chunks.extend(normalized)
            self._vectors = new_matrix
            if embedding_id:
                self._embedding_meta = {"embedding_id": embedding_id, "dims": int(new_matrix.shape[1])}
            self._save()

    def remove_document(self, doc_id):
        """Drop a document and all of its chunks; persist. Returns True if removed."""
        with self._lock:
            if doc_id not in self._documents:
                return False
            keep_rows = [i for i, c in enumerate(self._chunks) if c["doc_id"] != doc_id]
            self._chunks = [self._chunks[i] for i in keep_rows]
            if self._vectors is not None and self._vectors.size:
                self._vectors = self._vectors[keep_rows]
            del self._documents[doc_id]
            self._save()
            return True

    def reset(self):
        with self._lock:
            self._documents = {}
            self._chunks = []
            self._vectors = None
            self._embedding_meta = None
            self._save()

    # ------------------------------------------------------------------ search
    def search(self, query_vector, top_k: int, min_similarity: float, near_duplicate_cutoff: float = 0.95, embedding_id=None):
        """Cosine search with a similarity floor and near-duplicate suppression.

        Returns a list of {"chunk": chunk_dict, "score": float} in *selection*
        order (best first). Query vector must already be L2-normalized.
        `embedding_id` is checked against the index's recorded identity so a
        provider/model switch cannot silently compare incompatible vectors.
        """
        with self._lock:
            if self._vectors is None or not self._chunks:
                return []
            self._check_embedding_identity(embedding_id, vectors_shape=None)
            matrix = self._vectors
            q = np.asarray(query_vector, dtype=np.float32).reshape(1, -1)
            if q.shape[1] != matrix.shape[1]:
                raise AppError(
                    "index_failure",
                    "Query embedding size does not match the index. Clear the library and re-upload.",
                    500,
                )
            scores = (matrix @ q.T).reshape(-1)  # cosine: rows are normalized

            order = np.argsort(-scores)
            selected = []
            selected_vectors = []
            for idx in order:
                score = float(scores[idx])
                if score < min_similarity:
                    break
                vec = None
                if near_duplicate_cutoff < 1.0:
                    vec = matrix[idx]
                    duplicate = any(float(vec @ sv) > near_duplicate_cutoff for sv in selected_vectors)
                    if duplicate:
                        continue
                selected.append({"chunk": self._chunks[int(idx)], "score": score})
                if vec is not None:
                    selected_vectors.append(vec)
                if len(selected) >= top_k:
                    break
        return selected

    # ------------------------------------------------------------ identity guard
    def _check_embedding_identity(self, embedding_id, vectors_shape=None):
        """Refuse mixing vectors from different embedding models.

        Must be called while holding self._lock. If the index predates the
        identity metadata, it is treated as a legacy index and any modern
        embedding_id triggers the migration error.
        """
        if not embedding_id:
            return
        index_is_empty = not self._chunks and (
            self._vectors is None or self._vectors.size == 0
        )
        meta = self._embedding_meta
        if meta is None:
            if index_is_empty:
                return  # empty index — any provider may claim it
            # Index exists but was written by an older DocWiz (no meta file).
            meta = {"embedding_id": LEGACY_EMBEDDING_ID, "dims": int(self._vectors.shape[1])}
            self._embedding_meta = meta
        elif index_is_empty:
            return  # stale meta from a fully-deleted library — allow the switch
        if meta.get("embedding_id") == embedding_id:
            return
        stored, dims_stored = meta.get("embedding_id"), meta.get("dims")
        if stored == LEGACY_EMBEDDING_ID:
            raise AppError(
                "embedding_model_changed",
                "This library was indexed with an older DocWiz embedding model, which is "
                "no longer the configured provider. Reset the library (Reset button or "
                "DELETE /api/reset) and re-upload your PDFs to re-index them.",
                409,
            )
        raise AppError(
            "embedding_model_changed",
            f"The embedding model changed: this index was built with '{stored}' (dims={dims_stored}) "
            f"but DocWiz is now configured for '{embedding_id}'. Vectors from different models "
            "cannot be compared — reset the library and re-upload your PDFs to re-index them.",
            409,
        )

    # ------------------------------------------------------------------ persistence
    def _save(self):
        try:
            self.index_dir.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(
                self.index_dir / VECTORS_FILE,
                vectors=self._vectors if self._vectors is not None else np.zeros((0, 0), dtype=np.float32),
            )
            (self.index_dir / CHUNKS_FILE).write_text(
                json.dumps(self._chunks, ensure_ascii=False), encoding="utf-8"
            )
            (self.index_dir / DOCUMENTS_FILE).write_text(
                json.dumps(self._documents, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (self.index_dir / INDEX_META_FILE).write_text(
                json.dumps(self._embedding_meta or {}, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as exc:
            logger.exception("Failed to persist the vector index")
            raise AppError("index_persistence_failure", "Could not save the index to disk.", 500) from exc

    def _load(self):
        docs_path = self.index_dir / DOCUMENTS_FILE
        chunks_path = self.index_dir / CHUNKS_FILE
        vectors_path = self.index_dir / VECTORS_FILE
        if not (docs_path.exists() and chunks_path.exists() and vectors_path.exists()):
            logger.info("No existing index found — starting with an empty library.")
            return
        try:
            self._documents = json.loads(docs_path.read_text(encoding="utf-8"))
            self._chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
            loaded = np.load(vectors_path)["vectors"]
            self._vectors = loaded if loaded.size else None
            meta_path = self.index_dir / INDEX_META_FILE
            if meta_path.exists():
                try:
                    self._embedding_meta = json.loads(meta_path.read_text(encoding="utf-8")) or None
                except ValueError:
                    self._embedding_meta = None
            if not isinstance(self._documents, dict) or not isinstance(self._chunks, list):
                raise ValueError("Index metadata files have unexpected shapes")
            self._migrate_legacy_chunks()
            if len(self._chunks) != (self._vectors.shape[0] if self._vectors is not None else 0):
                logger.warning("Index files out of sync — resetting the library.")
                self._documents, self._chunks, self._vectors, self._embedding_meta = {}, [], None, None
            logger.info(
                "Index restored: %s document(s), %s chunk(s).", self.document_count, self.chunk_count
            )
        except (OSError, ValueError, KeyError) as exc:
            logger.exception("Could not load the saved index — starting empty.")
            self._documents, self._chunks, self._vectors, self._embedding_meta = {}, [], None, None

    def _migrate_legacy_chunks(self):
        """Bring persisted chunks up to the canonical schema (in place).

        Indexes written by older DocWiz versions store chunks without a
        `filename` field (the bug that crashed the LLM context builder with
        KeyError: 'filename'). The filename is recovered from the document
        registry — no re-indexing is needed: only metadata changes, vectors
        are untouched. Chunks that are unrecoverable (missing doc_id/text,
        or an unknown doc_id) are dropped and the vector matrix is realigned
        so retrieval can never emit malformed results.
        """
        if not self._chunks:
            return
        cleaned, keep_rows, updated, dropped = [], [], 0, 0
        for row, chunk in enumerate(self._chunks):
            clean = _normalize_chunk(chunk, self._documents.get(chunk.get("doc_id")) if isinstance(chunk, dict) else None)
            if clean is None:
                dropped += 1
                continue
            if clean != chunk:
                updated += 1
            cleaned.append(clean)
            keep_rows.append(row)
        if not dropped and not updated:
            return
        self._chunks = cleaned
        if self._vectors is not None and self._vectors.size:
            realigned = self._vectors[keep_rows] if keep_rows else self._vectors[:0]
            self._vectors = realigned if realigned.size else None
        # Keep the registry's display counts consistent with reality.
        counts = {}
        for c in cleaned:
            counts[c["doc_id"]] = counts.get(c["doc_id"], 0) + 1
        for doc_id, doc in self._documents.items():
            if doc_id in counts and doc.get("chunk_count") != counts[doc_id]:
                doc["chunk_count"] = counts[doc_id]
        logger.info(
            "Chunk metadata migrated to the canonical schema: %s updated, %s dropped.",
            updated,
            dropped,
        )
        self._save()
