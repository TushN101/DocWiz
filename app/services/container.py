"""Shared service singletons attached to the Flask app.

One EmbeddingService (lazy) + one VectorStore are shared by all requests,
so the embedding model loads exactly once and the index stays consistent.
"""
import threading

from app.services.pdf_service import validate_upload  # re-export for convenience  # noqa: F401


class ServiceContainer:
    def __init__(self, config):
        self.config = config
        self._embedder = None
        self._store = None
        self._rag = None
        # RLock (reentrant): lazy properties call each other (rag → embedder,
        # rag → store) while already holding the lock.
        self._lock = threading.RLock()

    @property
    def embedder_ready(self) -> bool:
        """True once the embedding model has actually been loaded."""
        return self._embedder is not None and self._embedder.loaded

    @property
    def store_ready(self) -> bool:
        return self._store is not None

    @property
    def embedder(self):
        if self._embedder is None:
            with self._lock:
                if self._embedder is None:
                    from app.services.embedding_service import build_embedding_service

                    self._embedder = build_embedding_service(self.config)
        return self._embedder

    @property
    def store(self):
        if self._store is None:
            with self._lock:
                if self._store is None:
                    from app.services.vector_store import VectorStore

                    self._store = VectorStore(self.config["INDEX_DIR"])
        return self._store

    @property
    def rag(self):
        if self._rag is None:
            with self._lock:
                if self._rag is None:
                    from app.services.rag_service import RagService

                    self._rag = RagService(self.embedder, self.store, _ConfigProxy(self.config))
        return self._rag


class _ConfigProxy:
    """Attribute-style access to Flask config values (cfg.TOP_K etc.)."""

    def __init__(self, config):
        self._config = config

    def __getattr__(self, name):
        try:
            return self._config[name]
        except KeyError:
            raise AttributeError(name)
