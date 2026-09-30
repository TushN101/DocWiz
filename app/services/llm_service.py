"""Groq LLM integration (model: openai/gpt-oss-120b) via the OpenAI-compatible
REST API, called with `requests` to keep the dependency footprint minimal.

Security: the API key lives in the environment, is used only in the
Authorization header server-side, and is never logged.
"""
import logging

import requests

from app.utils.errors import AppError

logger = logging.getLogger("docwiz.llm")

# ---------------------------------------------------------------------------
# Grounding system prompt — the heart of hallucination control (spec §5).
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are DocWiz, a careful document assistant. You answer questions using ONLY the context passages provided in the user's message, which are excerpts from documents the user uploaded.

Grounding rules:
1. Base your answer strictly on the provided context passages. They are your primary source of truth.
2. If the context passages contain the answer, give it directly and cite nothing yourself — the application attaches source references automatically.
3. If the context passages do not contain enough information to answer, say so plainly: state that the uploaded documents do not cover it. You may then optionally add clearly-labeled general knowledge in a separate short paragraph that begins with "General knowledge:" so it is never confused with document content.
4. NEVER invent facts, page numbers, section names, or quotations. NEVER claim something came from a document when it is not in the context.
5. If different passages conflict, point out the conflict instead of picking one silently.
6. Be concise and well-structured by default (short paragraphs or a compact list). Only elaborate when the question explicitly asks for depth or detail.
7. Answer in the same language as the question."""

MAX_CHUNK_CHARS_IN_CONTEXT_DEFAULT = 2600


def build_user_message(question: str, retrieved) -> str:
    """Assemble the context block + question.

    `retrieved` is a list of {"chunk": {...}, "score": float} in document order.
    Every chunk must follow the canonical schema —
    {"doc_id", "chunk_id", "filename", "text", "page_start", "page_end"} —
    which chunking_service stamps at creation and vector_store enforces on
    write and on load. Source attribution (filename + pages) therefore always
    survives the full retrieval pipeline.
    """
    parts = ["Context passages from the user's uploaded documents:", ""]
    for i, hit in enumerate(retrieved, start=1):
        chunk = hit["chunk"]
        pages = _format_pages(chunk)
        text = chunk["text"].strip()
        if len(text) > MAX_CHUNK_CHARS_IN_CONTEXT_DEFAULT:
            text = text[:MAX_CHUNK_CHARS_IN_CONTEXT_DEFAULT].rsplit(" ", 1)[0] + "…"
        parts.append(f"[{i}] Source: \"{chunk['filename']}\" — {pages}")
        parts.append(text)
        parts.append("")
    parts.append("---")
    parts.append(f"Question: {question.strip()}")
    parts.append(
        "Answer the question using only the context passages above. "
        "If they are insufficient, follow your grounding rules."
    )
    return "\n".join(parts)


def _format_pages(chunk) -> str:
    if chunk.get("page_end") and chunk["page_end"] != chunk.get("page_start"):
        return f"pages {chunk['page_start']}–{chunk['page_end']}"
    return f"page {chunk.get('page_start', '?')}"


def answer_question(
    question: str,
    retrieved,
    api_key: str,
    api_url: str,
    model: str,
    temperature: float,
    top_p: float,
    max_tokens: int,
    timeout: int,
) -> str:
    """Call Groq chat completions; return the assistant's answer text."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_message(question, retrieved)},
        ],
        "temperature": temperature,
        "top_p": top_p,
        "max_completion_tokens": max_tokens,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=timeout)
    except requests.exceptions.Timeout as exc:
        logger.error("Groq request timed out after %ss", timeout)
        raise AppError(
            "llm_timeout",
            "The AI service took too long to respond. Please try again.",
            504,
        ) from exc
    except requests.exceptions.ConnectionError as exc:
        logger.error("Cannot reach Groq API: %s", exc)
        raise AppError(
            "llm_network_error",
            "Could not reach the AI service. Check your internet connection and try again.",
            502,
        ) from exc

    if response.status_code == 401:
        raise AppError(
            "llm_auth_failed",
            "The Groq API key was rejected. Check GROQ_API_KEY in your .env file and restart DocWiz.",
            502,
        )
    if response.status_code == 404:
        raise AppError(
            "llm_model_unavailable",
            f"The model '{model}' is not available on Groq. Check the model name in your configuration.",
            502,
        )
    if response.status_code == 413:
        raise AppError(
            "llm_context_too_large",
            "The request exceeded the model's context window. Try reducing retrieval settings.",
            502,
        )
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "")
        hint = f" Please wait {retry_after.strip()} seconds and try again." if retry_after else " Please wait a moment and try again."
        raise AppError("llm_rate_limited", "Groq's free-tier rate limit was hit." + hint, 429)
    if response.status_code >= 400:
        logger.error("Groq API error %s: %s", response.status_code, response.text[:500])
        raise AppError(
            "llm_request_failed",
            "The AI service reported an error. Please try again in a moment.",
            502,
        )

    try:
        body = response.json()
        content = body["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        logger.error("Unexpected Groq response shape: %s", str(response.text[:500]))
        raise AppError(
            "llm_bad_response",
            "The AI service returned an unexpected response. Please try again.",
            502,
        ) from exc

    if not content or not content.strip():
        raise AppError(
            "llm_empty_answer",
            "The AI service returned an empty answer. Please rephrase and try again.",
            502,
        )
    # gpt-oss models can emit analysis/reasoning channels; message.content is the final answer.
    return content.strip()
