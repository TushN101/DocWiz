# DocWiz — Technical Research Report

## 1. Executive Summary

DocWiz is a **local-only** document-question-answering application (NotebookLM-style) built with a
**Flask** backend and a **vanilla HTML/CSS/JS** frontend. Users upload 2–3 PDFs; the backend
extracts text page-by-page, chunks it with page-aware metadata, embeds chunks with a local
Sentence-Transformers model (`all-MiniLM-L6-v2`, 384-dim), stores vectors in a lightweight
NumPy-backed local index, and answers questions through a Retrieval-Augmented Generation (RAG)
pipeline. Retrieved chunks — never whole PDFs — are sent to the **Groq API** using the model
`openai/gpt-oss-120b`. Every answer displays its source PDFs, page numbers, and short excerpts
taken verbatim from the retrieved chunks.

Core design principle: **the simplest stack that genuinely works on a student laptop**.
No Docker, no external database, no cloud services, no paid APIs (Groq's free tier suffices),
no frontend build tooling.

## 2. Requirements Recap

| Area | Requirement |
|---|---|
| Backend | Python 3.10+, Flask |
| Frontend | Vanilla HTML/CSS/JS only (no React/Vue/Angular/Next) |
| LLM | Groq API, model fixed to `openai/gpt-oss-120b` |
| Embeddings | Local, free, lightweight (no paid API) |
| Vector store | Lightweight, local, persistent across restarts, metadata-aware |
| PDF | Only PDF accepted; page boundaries preserved; graceful no-text handling |
| Citations | Filename + page number + verbatim excerpt; never fabricated |
| Security | API key server-side only; validated uploads; safe filenames; size limits |
| Deliverable | ZIP that runs after `pip install -r requirements.txt` + `.env` setup |

## 3. Architecture

```
┌───────────────────────────── Browser (vanilla JS SPA) ─────────────────────────────┐
│  Sidebar: document list, upload, status      Main: chat thread, sources, input     │
└──────────────┬─────────────────────────────────────────────────┬───────────────────┘
               │ POST /api/documents (multipart)                 │ POST /api/chat
               ▼                                                 ▼
┌──────────────────────────────────── Flask app ─────────────────────────────────────┐
│ routes (blueprint) → services                                                       │
│  ├─ pdf_service        validation (magic bytes + MIME), per-page text extraction    │
│  ├─ chunking_service   page-aware sliding window, overlap, sentence snapping        │
│  ├─ embedding_service  lazy singleton SentenceTransformer, batch encode             │
│  ├─ vector_store       NumPy matrix + JSON metadata, load/save to data/index/       │
│  ├─ rag_service        retrieve → threshold → MMR-lite → context build              │
│  └─ llm_service        Groq REST call, grounding system prompt, error mapping       │
└──────────────┬──────────────────────────────────────────────────────────────────────┘
               ▼
     data/uploads/*.pdf   data/index/{documents.json, chunks.json, vectors.npz}
```

**Why a service layer?** Routes stay thin (parse request → call service → format JSON).
Each service is independently testable, which the test suite exploits.

## 4. Technology Decisions (with alternatives considered)

### A. PDF extraction — **PyMuPDF (`fitz`)** ✅

| Option | Verdict | Reasoning |
|---|---|---|
| **PyMuPDF** | **Chosen** | Fastest pure-Python-callable extractor (~10× pdfplumber), excellent text quality incl. reading order, trivial per-page extraction (`page.get_text()`), tolerant of many malformed files, pure wheel install (no system deps). |
| pypdf | Rejected | Pure Python, safe install, but noticeably worse text reconstruction (spacing artifacts) and slower on large files. Good fallback but not primary. |
| pdfplumber | Rejected | Great for tables, but heavy for plain prose extraction and slow (pdfminer core). |
| pdfminer.six | Rejected | Accurate but very slow; API is low-level. |

PyMuPDF is AGPL-licensed — acceptable for a non-commercial, local college project (documented
in the README). Text extraction is per-page, so **page boundaries are preserved by design**.
Pages with no extractable text (scans/images) are detected and reported honestly; **no OCR is
performed** (documented limitation).

### B. Chunking strategy — **page-aware sliding window, sentence-snapped** ✅

- Chunk target ≈ **1,100 characters** (~220 tokens) with **180-character overlap** — small
  enough for precise retrieval, large enough to carry a complete idea.
- Pages are concatenated with page-offset tracking; a sliding window then cuts chunks while a
  side-index maps every character offset back to its page number, so each chunk knows exactly
  which page(s) it came from (`page_start` / `page_end`).
- Cut points snap to the **last sentence boundary** (`. ! ?` + whitespace) inside the window
  when one exists, avoiding mid-sentence chunks that damage embedding quality.
- Very short pages (e.g., a heading-only page) are merged forward so we never index useless
  20-character chunks.

Alternatives considered: fixed character chunks without overlap (loses boundary context),
RecursiveCharacterTextSplitter semantics (good, but pulling in LangChain for one function is an
unnecessary dependency for a college project — the logic is ~60 lines and now testable directly),
token-based chunking (requires a tokenizer; character approximation is adequate for prose).

### C. Embedding model — **`sentence-transformers/all-MiniLM-L6-v2`** ✅

| Model | Params | Dim | Speed (CPU) | Quality |
|---|---|---|---|---|
| **all-MiniLM-L6-v2** | 22M | 384 | ~1,500 sent/s | Strong (38.3 avg on BEIR-style retrieval tasks; MTEB retrieval ≈ 41.9) |
| bge-small-en-v1.5 | 33M | 384 | ~900 sent/s | Slightly better retrieval; needs "query:" prefixes handled correctly |
| all-mpnet-base-v2 | 109M | 768 | ~300 sent/s | Best of the three but 5× slower, 420 MB |
| OpenAI embeddings API | — | — | — | Rejected: paid API + cloud (violates local-first requirement) |

**Chosen: all-MiniLM-L6-v2.** Best speed/quality/size trade-off for a student machine: ~90 MB
download, 384-dim vectors, sub-millisecond query embedding on CPU, no GPU needed, MIT license,
works fully offline after first download. Model weights are cached by the library
(`~/.cache/huggingface`); nothing is baked into the repo.

### D. Vector store — **built-in NumPy cosine index (JSON + `.npz` persistence)** ✅

| Option | Verdict | Reasoning |
|---|---|---|
| **NumPy brute-force cosine** | **Chosen** | Exact search over a `(N, 384)` float32 matrix via one matmul: **< 5 ms for N = 10,000** on a laptop CPU — far beyond this app's scale (2–3 PDFs ≈ 500–3,000 chunks). Zero extra dependencies, ~120 lines, trivially persistent and debuggable. |
| FAISS (`faiss-cpu`) | Rejected | Excellent at million-vector scale, but adds a binary dependency with occasional install friction on Windows/older Linux, version-pinning headaches, and its IndexFlatIP adds nothing at this scale. |
| Chroma | Rejected | Heaviest option: pulls sqlite version constraints, ONNX runtime, telemetry service, its own embedding defaults to fight with. Overkill for a local college project. |
| LanceDB / Qdrant local | Rejected | New binary formats/concepts with no benefit at this scale. |

**Design:** vectors live in a float32 matrix; chunk texts + metadata (`doc_id`, `filename`,
`page_start`, `page_end`, `chunk_id`, `text`) live in a JSON list; a separate
`documents.json` registry tracks documents (id, safe filename, page count, chunk count, upload
time, status). Persistence = save matrix to `vectors.npz` + JSON files after each mutation.
Deletion removes a document's rows and rewrites the matrix. The store is a singleton owned by
the app so all requests share one consistent index.

### E. Retrieval strategy — **cosine top-k + similarity threshold + MMR-lite** ✅

1. Embed the question with the same model (normalized output → cosine = dot product).
2. Score all chunks; keep those with **cosine ≥ 0.20** (empirically separates "topical" from
   "noise" for MiniLM without being aggressive).
3. Take **top-k = 5** by score.
4. **MMR-lite diversity pass**: greedily drop a candidate whose cosine with an
   already-selected chunk exceeds **0.95** (near-duplicate spans), and try to keep coverage
   across different documents when scores are close. This is a deliberately light-touch
   alternative to a full MMR/λ reranker — at k=5 the heavy machinery is not worth it.
5. Assemble context: chunks in original document order (not score order) with numbered
   source tags `[1]`, `[2]`… so the model and the UI can reference them consistently.

**Cross-document behavior:** retrieval is global over the whole index, so relevance — not
document identity — decides which PDF contributes. The TCP-congestion-control example from the
spec falls out naturally: only chunks about the topic score above threshold.

### F. Reranking — **intentionally omitted (documented)**

Cross-encoder rerankers (e.g. `ms-marco-MiniLM-L-6-v2`) add a second model download and
double latency for a modest gain at k=5. The threshold + MMR-lite pass covers the practical
failure mode (near-duplicate chunks). This is recorded as a known, deliberate trade-off.

### G. Groq API integration — **raw REST via `requests`** ✅

Groq exposes an **OpenAI-compatible** API: `POST https://api.groq.com/openai/v1/chat/completions`
with `Authorization: Bearer $GROQ_API_KEY`. Using `requests` directly avoids the (version-
sensitive) `openai` SDK dependency and keeps the call surface tiny and auditable. The key is
read from the environment server-side and **never** sent to the frontend, never logged.

### H. `openai/gpt-oss-120b` usage ✅

- Model id passed verbatim as `model: "openai/gpt-oss-120b"`.
- gpt-oss-120b is a 117B-parameter MoE (≈5.1B active) with **128k context**, chat
  completions-compatible, available in Groq's free tier.
- Sampling: `temperature 0.2`, `top_p 0.9` for grounded, low-creativity answers;
  `max_completion_tokens ≈ 2048`; `stream: false` (a local app does not need SSE complexity).
- Response text = `choices[0].message.content`.

### I. Context-window considerations ✅

| Quantity | Value |
|---|---|
| Model context window | 131,072 tokens |
| Prompt + answer budget we target | ≤ ~8k tokens (fast, cheap, safe) |
| Retrieved context cap | **12,000 characters** (~3k tokens) across ≤ 5 chunks |
| Per-chunk cap in context | 2,600 chars (a full chunk is ~1,100, so this is a backstop) |
| Per-doc extraction cap | 1.5M chars; extraction stops at 200 pages (configurable) with a notice |

Because retrieval feeds only top-k chunks, **PDF size does not grow the prompt** — a 3-page or
300-page PDF costs the same context. Extremely large PDFs are handled by the page/extraction
caps plus a clear message; the index still covers the processed portion.

### J. Prompt structure ✅

- **System prompt** (constant, in `llm_service.py`): establishes the role ("answering strictly
  from provided context"), the grounding rules (prefer document info; never invent; say
  "the documents don't contain…" when insufficient; concise by default; never fabricate
  citations), and the answer format.
- **User message**: `Context` block — each chunk as
  `[n] (filename, page X): <text>` — followed by the `Question`.
- The model is told citations are handled by the app; it must not invent page numbers.

### K. Source citation strategy ✅

Sources are **derived from retrieval, not from the LLM**: the chunks actually placed in context
are the sources shown. The answer payload groups them per document with page numbers and a
verbatim excerpt (first ~240 chars of the chunk, trimmed at a word/sentence boundary). Since
excerpts are cut from the retrieved chunk text itself, **fabricated quotations are impossible**.

### L. Local persistence strategy ✅

```
data/
├── uploads/    original PDFs (renamed to <doc_id>__<safe-name>.pdf)
├── index/      documents.json (registry), chunks.json (texts+metadata), vectors.npz (matrix)
```

Everything survives restart: on boot the store reloads from `data/index/`. Chat history is
**session-only** (browser memory) — documented. `.gitignore` excludes `data/`, `.env`,
`.venv/`, `__pycache__/`.

### M. Flask architecture ✅

App-factory pattern (`create_app()` in `app/__init__.py`) + one API blueprint + service modules.
Configuration centralized in `config.py` (env-overridable: chunk size/overlap, top-k,
threshold, upload limits, model names). Long-lived singletons (embedder, vector store) are
initialized lazily and attached to the app.

### N. Frontend architecture ✅

Single `index.html` + `style.css` + `app.js`. No framework, no build step. State is a small JS
object (documents, messages, busy flags); rendering is plain DOM manipulation. All network I/O
via `fetch`. Fonts bundled locally in `static/fonts/` (Poppins / Lato / Lora — see
`design-choices.md`).

### O. Performance considerations ✅

- Embedding model loaded **once** (lazy singleton), batch encoding for chunks.
- First upload warms the model (~1–3 s); subsequent chunks embed in milliseconds.
- Retrieval is a single matmul (< 5 ms at this scale); Groq on LPU typically answers in ~1–3 s.
- Upload processing is synchronous for 2–3 PDFs (extraction + embedding a 300-page PDF takes
  only a few seconds with MiniLM on CPU).

### P. Error handling ✅

Every failure maps to a JSON body `{ "error": { "code", "message" } }` with an appropriate HTTP
status. Handled cases: non-PDF upload, fake/corrupt PDF (magic-byte check), empty/no-text PDF,
oversized file, embedding/model failure, index failure, missing `GROQ_API_KEY` (surfaced as a
clear 503 with setup hint), Groq 401/404/413/429 (rate limit, honors `Retry-After`),
network timeout (30 s), empty question, no relevant context (answered without calling the LLM).
The frontend renders these as friendly banners/messages, never tracebacks; full details go to
the server log only.

### Q. PDF size constraints ✅

30 MB per-file upload cap, ≤ 5 files per request, ≤ 5 documents per session (defaults, all
configurable). See context table in §I for extraction caps.

### R. Free-tier API constraints ✅

Groq free tier rate limits are model- and day-dependent (on the order of dozens of requests per
minute and a daily token cap). DocWiz is single-user local, so it stays far below request-rate
limits; a 429 handler with `Retry-After` support covers bursts, and the no-context short-circuit
avoids burning requests on questions the documents cannot answer.

## 5. Data Flow (happy path)

```
Upload  → validate (ext + magic bytes) → save file → per-page extract
        → page-aware chunking (+metadata) → batch embed → append to index → persist → respond
Question → embed query → cosine scores → threshold filter → top-k → MMR-lite
        → build context → Groq chat completion → answer + sources (doc, page, excerpt)
```

## 6. API Design

| Method | Route | Purpose |
|---|---|---|
| GET | `/` | Serve the SPA |
| GET | `/api/health` | Status: index stats, model loaded, API key presence (boolean only) |
| GET | `/api/documents` | List indexed documents |
| POST | `/api/documents` | Upload 1–5 PDFs (multipart) |
| DELETE | `/api/documents/<doc_id>` | Remove a document and its chunks from index |
| POST | `/api/chat` | `{ "question": "..." }` → answer + sources |
| POST | `/api/reset` | Clear the whole library (dev convenience) |

## 7. Installation Requirements (resulting from research)

```
flask>=3.0          web framework
python-dotenv>=1.0  .env loading
pymupdf>=1.24       PDF extraction
sentence-transformers>=3.0  local embeddings
numpy>=1.26         vector math + persistence
requests>=2.31      Groq REST calls
pytest>=8.0         tests (dev)
```

`torch` is installed automatically as a `sentence-transformers` dependency (CPU wheels are
sufficient; instructions included in README for CPU-only install to save disk space).

## 8. Development Plan

1. Backend services bottom-up: pdf → chunking → embeddings → vector store → RAG → LLM.
2. Routes + config + error mapping.
3. Frontend (layout → upload flow → chat flow → sources → states → polish).
4. Test suite (pytest, no network required; live-Groq test auto-skipped without a key).
5. Review pass, visual QA in a real browser, packaging.

## 9. Limitations (documented up front)

- **No OCR**: scanned/image-only PDFs yield a clear "no extractable text" message.
- English-centric retrieval (MiniLM-L6-v2 is English-optimized; other languages degrade).
- Chat history is not persisted across refreshes (by design for a local demo).
- gpt-oss-120b may include its native reasoning traces in `message.reasoning`; DocWiz uses only
  `message.content` for the answer.
- Text-layout PDFs only: complex multi-column scientific layouts may interleave column text in
  extraction order.

---

## Addendum (2026-09-30) — Embedding architecture revision: remote providers by default

**Trigger.** Deployment constraint on a small Debian VM (30 GB disk): installing
`sentence-transformers` pulls PyTorch, and the default Linux x86_64 torch wheel bundles the
CUDA/NVIDIA stack (multi-GB) even though only CPU inference is needed. The embedding step was
the only reason the project needed torch at all.

**Provider research (verified against primary docs on 2026-09-30).**

| Option | Verdict |
|---|---|
| Groq embeddings | `POST /openai/v1/embeddings` now exists (official OpenAPI schema); model `nomic-embed-text-v1_5` (768-d). Kept as an *optional* preset — not default (user prefers to conserve Groq quota for the LLM). |
| **Gemini API (chosen default)** | `POST /v1beta/models/{model}:embedContent` and `:batchEmbedContents`, auth via `x-goog-api-key`. `gemini-embedding-001`: text-only, supports `task_type` (`RETRIEVAL_DOCUMENT`/`RETRIEVAL_QUERY`) and Matryoshka `output_dimensionality` (recommended 768/1536/3072; default 3072). Free tier with per-project RPM/TPM/RPD quotas. |
| Jina AI | OpenAI-compatible `/v1/embeddings`, `jina-embeddings-v3`, 10M free tokens for new keys — reachable through the generic `openai-compatible` provider. |
| Mistral / OpenAI | OpenAI-compatible endpoints; paid. Also reachable via `openai-compatible`. |
| Local torch-free | `fastembed` (ONNX Runtime) exists, but an external API is practical here, so no new local dependency was added. |

**Design.** Only `embedding_service.py` changed in shape: the Sentence-Transformers singleton
became a provider facade with the *same* public interface (`embed_documents`, `embed_query`,
`loaded`). Providers: `gemini` (default), `openai-compatible`, `groq`, `hashing` (built-in
offline lexical encoder used by the test suite), `local` (legacy, optional install). Free-tier
resilience: request batching, retries on 429/5xx honouring `Retry-After`, and a content-
addressed disk cache (`data/embedding_cache.npz`) so re-indexing identical text costs nothing.

**Index compatibility.** Embeddings from different models are not comparable, so the store now
persists its embedding identity (`data/index/index_meta.json`) and refuses mixing with a
409 `embedding_model_changed` error that tells the user to reset and re-upload. Legacy indexes
(present before this change, built with MiniLM) are detected by the missing metadata file and
treated as incompatible with any new provider.

**Consequences.** requirements.txt no longer includes sentence-transformers (moved to
requirements-local.txt as an explicit opt-in). The default install is ~100 MB, CPU-only, and
fits comfortably on a small VM. Chunk text + questions are sent to the embedding provider
(Google by default); users who need zero external embedding calls can point
`openai-compatible` at a local Ollama server or opt into `local`.
