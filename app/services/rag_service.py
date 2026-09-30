"""RAG orchestration: retrieve → filter → build context → LLM → sources.

The pipeline guarantees that displayed sources are exactly the chunks that
were placed into the LLM context — citations can never be fabricated.
"""
import logging

from app.services import llm_service
from app.utils.errors import AppError
from app.utils.text import extract_excerpt

logger = logging.getLogger("docwiz.rag")

NO_CONTEXT_MESSAGE = (
    "I couldn't find anything about that in your uploaded documents. "
    "Try rephrasing the question, or check that the relevant PDFs have been uploaded."
)


class RagService:
    def __init__(self, embedder, store, config):
        self.embedder = embedder
        self.store = store
        self.config = config

    def answer(self, question: str) -> dict:
        question = (question or "").strip()
        if not question:
            raise AppError("empty_question", "Please type a question before sending.", 400)
        if len(question) > self.config.MAX_QUESTION_CHARS:
            raise AppError(
                "question_too_long",
                f"Questions are limited to {self.config.MAX_QUESTION_CHARS} characters.",
                400,
            )
        if self.store.is_empty():
            raise AppError(
                "no_documents",
                "There are no documents to search yet. Upload one or more PDFs first.",
                400,
            )
        if not self.config.GROQ_API_KEY or self.config.GROQ_API_KEY == "your_groq_api_key_here":
            raise AppError(
                "api_key_missing",
                "No Groq API key is configured. Add GROQ_API_KEY to your .env file and restart DocWiz.",
                503,
            )

        # 1. Embed the question and retrieve candidate chunks.
        query_vector = self.embedder.embed_query(question)
        hits = self.store.search(
            query_vector,
            top_k=self.config.TOP_K,
            min_similarity=self.config.MIN_SIMILARITY,
            near_duplicate_cutoff=self.config.NEAR_DUPLICATE_CUTOFF,
            embedding_id=getattr(self.embedder, "embedding_id", None),
        )

        if not hits:
            # Honest "not in the documents" answer — no LLM call, no fabricated content.
            return {
                "answer": NO_CONTEXT_MESSAGE,
                "sources": [],
                "grounded": False,
                "model": None,
            }

        # 2. Keep results in document order (reading order beats score order for coherence).
        hits = _sort_document_order(hits)

        # 3. Respect the context budget: include chunks until the char cap.
        included, used = [], 0
        for hit in hits:
            cost = min(len(hit["chunk"]["text"]), self.config.MAX_CHUNK_CHARS_IN_CONTEXT) + 40
            if included and used + cost > self.config.MAX_CONTEXT_CHARS:
                break
            included.append(hit)
            used += cost

        # 4. Ask the LLM.
        answer_text = llm_service.answer_question(
            question=question,
            retrieved=included,
            api_key=self.config.GROQ_API_KEY,
            api_url=self.config.GROQ_API_URL,
            model=self.config.GROQ_MODEL,
            temperature=self.config.GROQ_TEMPERATURE,
            top_p=self.config.GROQ_TOP_P,
            max_tokens=self.config.GROQ_MAX_COMPLETION_TOKENS,
            timeout=self.config.GROQ_TIMEOUT_SECONDS,
        )

        # 5. Sources = exactly the chunks that went into the context.
        # `filename` is part of the canonical chunk schema (stamped at chunking
        # time, enforced by the vector store on write and load); the registry
        # lookup is only a defensive fallback for unusual metadata.
        sources = []
        for hit in included:
            chunk = hit["chunk"]
            sources.append(
                {
                    "doc_id": chunk["doc_id"],
                    "filename": chunk.get("filename") or self.store.filename_for(chunk["doc_id"]),
                    "page_start": chunk["page_start"],
                    "page_end": chunk["page_end"],
                    "chunk_id": chunk["chunk_id"],
                    "excerpt": extract_excerpt(chunk["text"], self.config.EXCERPT_CHARS),
                    "score": round(hit["score"], 4),
                }
            )
        return {"answer": answer_text, "sources": sources, "grounded": True, "model": self.config.GROQ_MODEL}


def _sort_document_order(hits):
    """Group hits by document, keeping each group in page order; best-scored doc first."""
    by_doc = {}
    for hit in hits:
        by_doc.setdefault(hit["chunk"]["doc_id"], []).append(hit)
    groups = sorted(
        by_doc.values(),
        key=lambda group: -max(hit["score"] for hit in group),
    )
    ordered = []
    for group in groups:
        ordered.extend(sorted(group, key=lambda h: (h["chunk"]["page_start"], h["chunk"]["page_end"])))
    return ordered
