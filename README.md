# DocWiz 📄

**A local, private "chat with your PDFs" assistant.** Upload a few PDFs, ask questions in plain
language, and get answers grounded in your documents — complete with the exact source file,
page numbers, and short excerpts. Nothing is stored in the cloud: your PDFs and the search
index live on your machine.

Inspired by NotebookLM-style document Q&A. Built with Python + Flask and a vanilla
HTML/CSS/JavaScript frontend.

---

## 1. What is DocWiz?

DocWiz is a small Retrieval-Augmented Generation (RAG) application that runs on your computer.
Text never goes to the cloud except in two small, configurable places: the **embedding
provider** (question + retrieved passages, in order to find and rank relevant text) and the
**Groq LLM API** (the retrieved passages + your question, in order to write the answer).
Instead of stuffing whole PDFs into a chatbot, DocWiz **indexes** your documents: it extracts
the text page-by-page, splits it into passages ("chunks"), embeds them via the configured
provider, and stores the vectors in a lightweight local index. When you ask a question, only
the handful of most relevant passages are retrieved and sent to the LLM — which keeps answers
fast, focused, and cheap.

## 2. Features

- 📄 **PDF upload** (drag & drop or browse) — 1–5 files at a time, PDFs only
- 🔍 **Real RAG pipeline** — extract → page-aware chunking → embeddings → vector search
- ☁️ **No PyTorch/CUDA needed** — embeddings come from a configurable provider
  (Gemini free tier by default; Jina, Mistral, Groq, Ollama and others supported)
- 🧠 **Grounded answers** via Groq (`openai/gpt-oss-120b`), with strict anti-hallucination rules
- 💸 **Free-tier friendly** — batched requests, automatic retries on rate limits, and a local
  embedding cache so re-uploading the same content never costs extra quota
- 📎 **Source citations on every answer** — filename + page number + verbatim excerpt
- 🗂 **Multiple documents** — search spans all uploaded PDFs; only relevant chunks are used
- 💾 **Persistent index** — your library survives server restarts
- 🎨 **Polished dark UI** — Claude-inspired visual language, Anthropic Sans/Serif typography,
  designed specifically for DocWiz
- 🔐 **Local-first** — the API key never leaves the server; documents never leave your machine

## 3. Architecture

```
Browser (vanilla JS SPA)
   │  POST /api/documents          POST /api/chat
   ▼
Flask (app factory + blueprints)
   ├─ pdf_service        validation (extension + MIME + magic bytes), per-page extraction
   ├─ chunking_service   page-aware sliding window, overlap, sentence snapping
   ├─ embedding_service  pluggable providers (Gemini · OpenAI-compatible · Groq · offline), cached
   ├─ vector_store       NumPy cosine index persisted to data/index/
   ├─ rag_service        retrieve → similarity floor → near-dup filter → context build
   └─ llm_service        Groq REST call + grounding system prompt + error mapping
   ▼
data/uploads/ (PDF files)      data/index/ (documents.json, chunks.json, vectors.npz)
```

See `research.md` for the full technology evaluation (why PyMuPDF, why a NumPy index instead
of FAISS/Chroma), `design-choices.md` for the UI design system, and the **Embedding providers**
section below for how embeddings are generated.

## 4. Prerequisites

- **Python 3.10 or newer** (`python --version` to check)
- A **free Groq API key** → create one at <https://console.groq.com/keys>
- A **free Google AI Studio key** for embeddings → create one at
  <https://aistudio.google.com/apikey> (generous free tier — see section 8)
- A few hundred MB of disk for the Python packages — **no PyTorch, no CUDA,
  no NVIDIA libraries required**

## 5. Python version

Python **3.10, 3.11, or 3.12** are supported. If `python` refers to Python 2 on your system, use
`python3` instead in every command below.

## 6. Installation

Unzip the project (if you received it as `docwiz.zip`) and open a terminal in the project
folder — the one containing `app.py`.

### 6. Virtual environment setup

**Windows:**
```bat
python -m venv .venv
.venv\Scripts\activate
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 7. Dependency installation

```bash
pip install -r requirements.txt
```

This is a small, CPU-only install (Flask, PyMuPDF, NumPy, requests). Embeddings are generated
by a remote provider, so **nothing multi-gigabyte is pulled in**. If you ever want fully local
embeddings instead, see `requirements-local.txt` — but it is not needed and pulls PyTorch.

## 8. `.env` setup

1. Copy the example file and rename the copy to `.env`:
   - Windows: `copy .env.example .env`
   - macOS/Linux: `cp .env.example .env`
2. Get your two free keys:
   - Groq (answers): <https://console.groq.com/keys>
   - Google AI Studio (embeddings): <https://aistudio.google.com/apikey>
3. Open `.env` and replace the placeholders:
   ```
   GROQ_API_KEY=gsk_...your key...
   EMBEDDING_API_KEY=AIza...your key...
   ```
4. Save. Both keys are read only by the Flask server, never by the browser.

(`.env` is listed in `.gitignore`, so keys can never be committed accidentally.)

### 8.1 Embedding providers

Embeddings are **pluggable** — pick the provider with `EMBEDDING_PROVIDER` and DocWiz handles
the rest (batching, retries, caching, L2-normalization). Defaults are sensible; you only set
the key:

| `EMBEDDING_PROVIDER` | Service / default model | Key (env var) | Notes |
|---|---|---|---|
| `gemini` *(default)* | Google AI Studio — `gemini-embedding-001`, 768-dim | `EMBEDDING_API_KEY` (or `GEMINI_API_KEY`) | Free tier; task-typed retrieval embeddings; 3072→768 Matryoshka truncation |
| `openai-compatible` | Any OpenAI-style `/embeddings` endpoint | `EMBEDDING_API_KEY` (optional for Ollama) | Set `EMBEDDING_API_BASE` + `EMBEDDING_MODEL` — e.g. Jina `https://api.jina.ai/v1` + `jina-embeddings-v3` (10M free tokens), Mistral `https://api.mistral.ai/v1` + `mistral-embed`, or local Ollama `http://localhost:11434/v1` |
| `groq` | Groq — `nomic-embed-text-v1_5` | shares `GROQ_API_KEY` | Optional preset; note Groq's free tier applies |
| `hashing` | Built-in offline lexical encoder (256-dim) | none | Zero network; keyword-level matching only (tests / emergency fallback) |
| `local` | Sentence-Transformers — `all-MiniLM-L6-v2` | none | Legacy behaviour; requires `pip install -r requirements-local.txt` (large PyTorch download) |

**Free-tier notes (Gemini):** Google AI Studio's free tier covers embedding models with
per-project RPM/TPM/RPD quotas (check your live numbers at <https://aistudio.google.com/rate-limit>).
DocWiz is built to respect them: chunk texts are batched into few requests, transient 429/5xx
responses are retried with backoff honouring `Retry-After`, and an on-disk cache
(`data/embedding_cache.npz`) reuses vectors for identical text — deleting and re-uploading the
same PDF costs zero extra quota.

**Switching providers or models later:** just change the env vars and restart. Embeddings from
different models live in different vector spaces, so DocWiz refuses to mix them: it records the
provider/model of the existing index (`data/index/index_meta.json`) and, on mismatch, raises a
clear `embedding_model_changed` error telling you to reset the library and re-upload your PDFs.
(The embedding cache is keyed by provider+model, so it stays correct across switches.)

## 9. How to start the Flask server

```bash
python app.py        # or: python3 app.py
```

The console prints a startup banner (including the active embedding provider). Keep this window
open while using DocWiz.

## 10. Where to open the application

Open your browser at:

**<http://127.0.0.1:5000>**

## 11. How to upload PDFs

1. In the left sidebar, click **Add PDFs** (or drag & drop files onto it — or anywhere on the
   page).
2. Wait for processing: each document appears in the sidebar with its page and passage count.
3. Type a question in the box at the bottom and press **Enter** (or the ↑ send button).

Limits (configurable in `config.py`): 30 MB per file, 5 files per upload, 5 documents in the
library, first 200 pages per PDF are indexed. Remove documents with the ✕ button on each row,
or clear everything with **Clear library**.

## 12. How RAG works (in DocWiz)

```
PDF upload → validation → per-page text extraction → page-aware chunking (~1,100 chars,
180 overlap) → embeddings via the configured provider (Gemini 768-dim by default) → vector
index (NumPy cosine)

Question → question embedding → cosine similarity search → top-5 passages above the
similarity floor (near-duplicates filtered) → context block → Groq (openai/gpt-oss-120b)
→ grounded answer → sources panel
```

Retrieval is **global across all uploaded PDFs**: a question about TCP congestion control will
pull passages from *Computer Networks.pdf*, not from the DBMS textbook that happens to be
uploaded too. Only those retrieved passages — never whole PDFs — are sent to the LLM, and the
context is capped (~12,000 characters) no matter how large your PDFs are.

## 13. How source citations work

Sources are **derived from retrieval, not from the model**: the passages actually placed into
the LLM context are the ones shown under each answer — grouped with the PDF filename, the page
number(s) they came from, and a short excerpt cut verbatim from the retrieved text. The model
is explicitly instructed not to invent page numbers or quotes, and DocWiz would filter out any
source that was not retrieved. If nothing relevant is found, DocWiz says so honestly instead of
guessing.

## 14. Project structure

```
docwiz/
├── app.py                 # entry point: python app.py
├── config.py              # all tunable settings (env-overridable)
├── requirements.txt       # small CPU-only install (no PyTorch)
├── requirements-local.txt # optional: fully local embeddings (pulls PyTorch)
├── .env.example           # copy to .env and add your API keys
├── research.md            # technology decisions & reasoning
├── design-choices.md      # UI/UX design system
├── design.md              # design tokens (Claude palette)
├── app/
│   ├── __init__.py        # Flask app factory
│   ├── routes/            # api.py (JSON API) · views.py (serves the SPA)
│   ├── services/          # pdf · chunking · embedding · vector_store · rag · llm
│   └── utils/             # errors (JSON error mapping) · text helpers
├── templates/index.html   # the single-page UI
├── static/
│   ├── css/style.css      # dark Claude-inspired theme
│   ├── js/app.js          # frontend logic (vanilla JS)
│   └── fonts/             # AnthropicSansVariable.woff2 · AnthropicSerifVariable.woff2 (see §Fonts)
├── data/                  # created at runtime — your uploads + index (git-ignored)
└── tests/                 # pytest suite (no API key needed)
```

## 15. Troubleshooting

| Symptom | Fix |
|---|---|
| **`KeyError: 'filename'` on chat (older installs)** | Fixed in the current release. Existing indexes migrate automatically on the next server start (filenames are recovered from `documents.json` — no re-upload needed). If you see the error anyway, reset the library once and re-upload. |
| **"API key missing" chip / `api_key_missing` error** | You skipped step 8, or the key is still the placeholder. Edit `.env`, then restart `python app.py`. |
| **`embedding_auth_failed` on upload** | The embedding key is wrong/revoked — regenerate it at aistudio.google.com/apikey and update `EMBEDDING_API_KEY` in `.env`. |
| **`embedding_rate_limited`** | The provider's free-tier quota was hit. Wait for the indicated time; the built-in cache means retrying the same content costs nothing extra. |
| **`embedding_model_changed`** | You switched embedding provider/model after indexing. Reset the library (Clear library) and re-upload your PDFs. |
| **"The Groq API key was rejected"** | The key is wrong or revoked — regenerate it at console.groq.com/keys. |
| **"Groq's free-tier rate limit was hit"** | Wait a few seconds/minutes (free tier has per-minute caps) and try again. |
| **"no extractable text" when uploading** | The PDF is scanned/image-only. DocWiz does **not** perform OCR — run OCR software on the file first. |
| **"not a valid PDF (corrupted or renamed file)"** | The file fails the PDF magic-byte check — it is broken or misnamed. |
| **First question is slow** | Nothing to pre-load any more — if anything feels slow, it is the provider round-trip; check your connection. |
| **`ModuleNotFoundError` after installing** | Your virtual environment is not active — redo the activation command from step 6. |
| **Port 5000 already in use** | Another app owns the port. Stop it, or change the port at the bottom of `app.py`. |
| **Answers feel generic** | Try more specific questions, raise `TOP_K`, or check that the relevant PDF is actually uploaded (see sidebar). |

Detailed logs are printed in the terminal where the server runs.

## 16. Known limitations

- **No OCR.** Scanned or image-only PDFs produce a clear error instead of answers.
- **English-centric retrieval.** The default Gemini embedding model is multilingual (100+),
  but the chunker's sentence-snapping heuristics are tuned on English text.
- **External embedding provider.** Chunk text and questions are sent to the embedding API to
  compute vectors (by default Google). For fully local/offline operation switch
  `EMBEDDING_PROVIDER` to `local` (PyTorch) or `hashing` (offline, lexical quality only), or
  point `openai-compatible` at a local Ollama server.
- **Complex layouts.** Multi-column scientific PDFs may extract text in visual order, which can
  slightly scramble chunk text.
- **Chat history is session-only.** Refreshing the browser clears the conversation (documents
  and the index persist).
- **Page cap.** Only the first 200 pages of each PDF are indexed (configurable via
  `MAX_PAGES_PER_PDF`); the UI tells you when a document was truncated.
- **PyMuPDF is AGPL-licensed.** Fine for this non-commercial, local college project — don't ship
  DocWiz commercially without reviewing licenses.

## 17. Fonts

DocWiz uses Anthropic's variable fonts for its UI:

- `static/fonts/AnthropicSansVariable.woff2` — primary UI/sans-serif face
- `static/fonts/AnthropicSerifVariable.woff2` — serif face used for the greeting, answers and
  source excerpts

Both are wired up with `@font-face` in `static/css/style.css` — just drop the two `.woff2` files
into `static/fonts/` and (re)start the server; no CSS changes are needed. Until the files are
present, the app falls back to the system font stack, so nothing breaks.

---

*Font files are not redistributed with this project. The stylesheet declares a full system-font
fallback stack, so the UI remains fully functional without them.*
