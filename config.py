"""Central configuration for DocWiz.

Every value can be overridden through environment variables (see .env.example),
so RAG behaviour is tunable without touching code. The Config class doubles as
the Flask app config (app.config["CHUNK_SIZE"] etc.).
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def ensure_storage():
    """Create the local data directories (uploads + index) if missing."""
    data_dir = Path(os.environ.get("DOCWIZ_DATA_DIR", BASE_DIR / "data"))
    (data_dir / "uploads").mkdir(parents=True, exist_ok=True)
    (data_dir / "index").mkdir(parents=True, exist_ok=True)


class Config:
    # ------------------------------------------------------------------
    # Storage (local filesystem only — no database)
    # ------------------------------------------------------------------
    DATA_DIR = Path(os.environ.get("DOCWIZ_DATA_DIR", BASE_DIR / "data"))
    UPLOAD_DIR = DATA_DIR / "uploads"
    INDEX_DIR = DATA_DIR / "index"

    # ------------------------------------------------------------------
    # Flask
    # ------------------------------------------------------------------
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "30")) * 1024 * 1024  # request body cap
    JSON_SORT_KEYS = False

    # ------------------------------------------------------------------
    # Groq LLM
    # ------------------------------------------------------------------
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
    GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
    GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
    GROQ_TIMEOUT_SECONDS = int(os.environ.get("GROQ_TIMEOUT_SECONDS", "45"))
    GROQ_TEMPERATURE = float(os.environ.get("GROQ_TEMPERATURE", "0.2"))
    GROQ_TOP_P = float(os.environ.get("GROQ_TOP_P", "0.9"))
    GROQ_MAX_COMPLETION_TOKENS = int(os.environ.get("GROQ_MAX_COMPLETION_TOKENS", "2048"))

    # ------------------------------------------------------------------
    # Embeddings (pluggable provider — no local PyTorch/CUDA needed)
    # ------------------------------------------------------------------
    # gemini              Google AI Studio free tier (default; EMBEDDING_API_KEY
    #                     or GEMINI_API_KEY)
    # openai-compatible   any OpenAI-style /embeddings endpoint (Jina, Mistral,
    #                     OpenAI, Ollama, …) — set EMBEDDING_API_BASE + EMBEDDING_MODEL
    # groq                Groq embeddings preset (nomic-embed-text-v1_5; shares
    #                     GROQ_API_KEY)
    # hashing             built-in offline lexical encoder (tests / fallback)
    # local               Sentence-Transformers (legacy; optional install)
    EMBEDDING_PROVIDER = os.environ.get("EMBEDDING_PROVIDER", "gemini").strip().lower()
    # Provider-agnostic API key. For gemini, GEMINI_API_KEY is also accepted;
    # for groq, GROQ_API_KEY is accepted as a fallback.
    EMBEDDING_API_KEY = os.environ.get("EMBEDDING_API_KEY", "").strip()
    EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "").strip()          # "" → provider default
    EMBEDDING_API_BASE = os.environ.get("EMBEDDING_API_BASE", "").strip()    # "" → provider default
    EMBEDDING_OUTPUT_DIMS = int(os.environ.get("EMBEDDING_OUTPUT_DIMS", "0"))  # 0 → provider default
    EMBEDDING_BATCH_SIZE = int(os.environ.get("EMBEDDING_BATCH_SIZE", "64"))   # texts per request
    EMBEDDING_TIMEOUT_SECONDS = float(os.environ.get("EMBEDDING_TIMEOUT_SECONDS", "30"))
    EMBEDDING_MAX_RETRIES = int(os.environ.get("EMBEDDING_MAX_RETRIES", "2"))  # extra attempts on 429/5xx
    EMBEDDING_CACHE = os.environ.get("EMBEDDING_CACHE", "1")                   # 0 disables the disk cache
    # Task types (Gemini only; improve asymmetric retrieval quality)
    EMBEDDING_TASK_DOCUMENT = os.environ.get("EMBEDDING_TASK_DOCUMENT", "RETRIEVAL_DOCUMENT")
    EMBEDDING_TASK_QUERY = os.environ.get("EMBEDDING_TASK_QUERY", "RETRIEVAL_QUERY")
    EMBEDDING_HASH_DIMS = int(os.environ.get("EMBEDDING_HASH_DIMS", "256"))    # hashing provider dims

    # ------------------------------------------------------------------
    # RAG pipeline tuning
    # ------------------------------------------------------------------
    CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "1100"))        # target chars per chunk
    CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "180"))   # chars carried between chunks
    MIN_CHUNK_CHARS = int(os.environ.get("MIN_CHUNK_CHARS", "80"))
    TOP_K = int(os.environ.get("TOP_K", "5"))                     # chunks sent to the LLM
    MIN_SIMILARITY = float(os.environ.get("MIN_SIMILARITY", "0.20"))  # cosine floor
    NEAR_DUPLICATE_CUTOFF = float(os.environ.get("NEAR_DUPLICATE_CUTOFF", "0.95"))
    MAX_CONTEXT_CHARS = int(os.environ.get("MAX_CONTEXT_CHARS", "12000"))  # chars of context sent to the LLM
    MAX_CHUNK_CHARS_IN_CONTEXT = int(os.environ.get("MAX_CHUNK_CHARS_IN_CONTEXT", "2600"))
    MAX_QUESTION_CHARS = int(os.environ.get("MAX_QUESTION_CHARS", "2000"))
    EXCERPT_CHARS = int(os.environ.get("EXCERPT_CHARS", "240"))   # excerpt shown per source in the UI

    # ------------------------------------------------------------------
    # Upload / document limits
    # ------------------------------------------------------------------
    MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "30"))
    MAX_FILES_PER_UPLOAD = int(os.environ.get("MAX_FILES_PER_UPLOAD", "5"))
    MAX_DOCUMENTS = int(os.environ.get("MAX_DOCUMENTS", "5"))
    MAX_PAGES_PER_PDF = int(os.environ.get("MAX_PAGES_PER_PDF", "200"))
    MAX_CHARS_PER_PDF = int(os.environ.get("MAX_CHARS_PER_PDF", "1500000"))
    # A document whose extractable text is below this many chars is treated as text-free.
    MIN_TOTAL_TEXT_CHARS = int(os.environ.get("MIN_TOTAL_TEXT_CHARS", "25"))
