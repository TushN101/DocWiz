"""JSON API routes: health, documents (list/upload/delete), chat, reset."""
import logging
import time
import uuid
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from app.services import pdf_service
from app.services.chunking_service import chunk_pages
from app.utils.errors import AppError
from app.utils.text import sanitize_filename

api_bp = Blueprint("api", __name__, url_prefix="/api")
logger = logging.getLogger("docwiz.api")


def _services():
    return current_app.extensions["docwiz"]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@api_bp.get("/health")
def health():
    svc = _services()
    if svc.store_ready:
        documents, chunks = svc.store.document_count, svc.store.chunk_count
    else:
        documents, chunks = 0, 0
    embedding_cfg = current_app.config
    return jsonify(
        {
            "status": "ok",
            "app": "DocWiz",
            "documents": documents,
            "chunks": chunks,
            "embedding_provider": embedding_cfg["EMBEDDING_PROVIDER"],
            "embedding_model": embedding_cfg["EMBEDDING_MODEL"] or _provider_default_model(embedding_cfg["EMBEDDING_PROVIDER"]),
            "embedding_model_loaded": svc.embedder_ready,
            "embedding_key_configured": _embedding_key_configured(embedding_cfg),
            "groq_model": current_app.config["GROQ_MODEL"],
            "api_key_configured": bool(current_app.config["GROQ_API_KEY"]),
        }
    )


def _provider_default_model(provider):
    from app.services.embedding_service import PROVIDER_DEFAULTS

    return PROVIDER_DEFAULTS.get(provider, {}).get("model", "")


def _embedding_key_configured(cfg):
    provider = cfg["EMBEDDING_PROVIDER"]
    if provider == "gemini":
        return bool(cfg.get("EMBEDDING_API_KEY") or cfg.get("GEMINI_API_KEY"))
    if provider == "groq":
        return bool(cfg.get("EMBEDDING_API_KEY") or cfg.get("GROQ_API_KEY"))
    return True  # openai-compatible / hashing / local need no key up front


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------
@api_bp.get("/documents")
def list_documents():
    docs = _services().store.list_documents()
    return jsonify({"documents": [_public_doc(d) for d in docs]})


@api_bp.post("/documents")
def upload_documents():
    files = request.files.getlist("files") or request.files.getlist("file")
    if not files:
        raise AppError("no_files", "No file was received. Attach at least one PDF.", 400)
    if len(files) > current_app.config["MAX_FILES_PER_UPLOAD"]:
        raise AppError(
            "too_many_files",
            f"Please upload at most {current_app.config['MAX_FILES_PER_UPLOAD']} PDFs per request.",
            400,
        )

    svc = _services()
    cfg = current_app.config
    results = []
    for storage in files:
        display_name = sanitize_filename(storage.filename or "")
        try:
            result = _process_one_pdf(svc, cfg, storage, display_name)
            results.append({"ok": True, "filename": display_name, **result})
        except AppError as err:
            logger.warning("Upload rejected for %s: %s", display_name, err.code)
            results.append(
                {"ok": False, "filename": display_name, "error": {"code": err.code, "message": err.message}}
            )

    accepted = [r for r in results if r["ok"]]
    status = 200 if accepted else 400
    return jsonify({"results": results, "documents": [_public_doc(d) for d in svc.store.list_documents()]}), status


def _process_one_pdf(svc, cfg, storage, display_name):
    if svc.store.document_count >= cfg["MAX_DOCUMENTS"]:
        raise AppError(
            "document_limit_reached",
            f"The library holds at most {cfg['MAX_DOCUMENTS']} documents. Remove one before adding another.",
            400,
        )

    data = pdf_service.validate_upload(storage, cfg["MAX_UPLOAD_MB"])
    pages, info = pdf_service.extract_pages(
        data,
        display_name,
        max_pages=cfg["MAX_PAGES_PER_PDF"],
        min_total_chars=cfg["MIN_TOTAL_TEXT_CHARS"],
        max_chars=cfg["MAX_CHARS_PER_PDF"],
    )

    doc_id = uuid.uuid4().hex[:12]
    chunks = chunk_pages(
        pages,
        doc_id,
        chunk_size=cfg["CHUNK_SIZE"],
        overlap=cfg["CHUNK_OVERLAP"],
        min_chunk_chars=cfg["MIN_CHUNK_CHARS"],
        filename=display_name,
    )
    if not chunks:
        raise AppError("no_extractable_text", f"'{display_name}' produced no indexable text.", 400)

    texts = [c["text"] for c in chunks]
    vectors = svc.embedder.embed_documents(texts)

    saved_path = cfg["UPLOAD_DIR"] / f"{doc_id}__{display_name}"
    saved_path.write_bytes(data)

    doc_meta = {
        "doc_id": doc_id,
        "filename": display_name,
        "stored_as": saved_path.name,
        "pages": info["total_pages"],
        "processed_pages": info["processed_pages"],
        "truncated": info["truncated"],
        "pages_without_text": len(info["empty_pages"]),
        "char_count": info["char_count"],
        "chunk_count": len(chunks),
        "size_bytes": len(data),
        "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    svc.store.add_document(doc_meta, chunks, vectors, embedding_id=getattr(svc.embedder, "embedding_id", None))
    logger.info(
        "Indexed %s: %s pages → %s chunks (truncated=%s)", display_name, info["total_pages"], len(chunks), info["truncated"]
    )
    return {"doc_id": doc_id, "pages": info["total_pages"], "chunks": len(chunks), "truncated": info["truncated"]}


@api_bp.delete("/documents/<doc_id>")
def delete_document(doc_id: str):
    svc = _services()
    doc = svc.store.get_document(doc_id)
    if not doc:
        raise AppError("document_not_found", "That document is no longer in the library.", 404)

    svc.store.remove_document(doc_id)
    stored_name = doc.get("stored_as", "")
    safe = Path(stored_name).name  # never trust stored names for path construction
    path = current_app.config["UPLOAD_DIR"] / safe
    try:
        if path.exists():
            path.unlink()
    except OSError:
        logger.warning("Could not delete stored file %s", safe)

    return jsonify({"ok": True, "removed": doc["filename"]})


@api_bp.post("/reset")
def reset_library():
    svc = _services()
    for doc in svc.store.list_documents():
        stored_name = Path(doc.get("stored_as", "")).name
        path = current_app.config["UPLOAD_DIR"] / stored_name
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass
    svc.store.reset()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------
@api_bp.post("/chat")
def chat():
    payload = request.get_json(silent=True) or {}
    question = payload.get("question", "")
    if not isinstance(question, str) or not question.strip():
        raise AppError("empty_question", "Please type a question before sending.", 400)

    answer = _services().rag.answer(question)
    return jsonify(answer)


# ---------------------------------------------------------------------------
def _public_doc(meta):
    return {
        "doc_id": meta["doc_id"],
        "filename": meta["filename"],
        "pages": meta["pages"],
        "chunk_count": meta["chunk_count"],
        "size_bytes": meta.get("size_bytes"),
        "truncated": meta.get("truncated", False),
        "uploaded_at": meta.get("uploaded_at"),
    }
