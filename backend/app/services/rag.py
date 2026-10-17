from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import ChatMessage
from app.services.cache import get_cached_answer, get_kb_version, save_cached_answer
from app.services.llm import generate_answer, is_follow_up, rewrite_follow_up
from app.services.retriever import RetrievalResponse, retrieve

logger = logging.getLogger(__name__)
NOT_FOUND_ANSWER = "I couldn't find this in the company documents."


def _prepare_question(
    question: str,
    history: list[dict[str, str]],
) -> str:
    if is_follow_up(question, history):
        return rewrite_follow_up(question, history[-6:])
    return question.strip()


def _citations(
    retrieval: RetrievalResponse,
    used_chunk_ids: list[str],
) -> list[dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    for index, chunk in enumerate(retrieval.results, start=1):
        citation = {
            "filename": chunk.filename,
            "page": chunk.page,
            "section": chunk.section,
            "snippet": chunk.text[:500],
        }
        sources[f"C{index}"] = citation
    return [sources[chunk_id] for chunk_id in used_chunk_ids if chunk_id in sources]


def answer_question(
    db: Session,
    question: str,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    if not question.strip():
        raise ValueError("Question must not be empty.")

    recent_history = (history or [])[-6:]
    kb_version = get_kb_version(db)
    cached = get_cached_answer(db, question, kb_version)
    if cached is not None:
        logger.info("Answer cache hit for normalized question.")
        return {**cached, "cached": True}

    standalone_question = _prepare_question(question, recent_history)
    if standalone_question != question.strip():
        cached = get_cached_answer(db, standalone_question, kb_version)
        if cached is not None:
            logger.info("Answer cache hit for standalone follow-up question.")
            save_cached_answer(
                db,
                question,
                ",".join(cached.get("buckets", [])),
                kb_version,
                cached,
            )
            return {**cached, "cached": True}

    retrieval = retrieve(standalone_question)
    cache_bucket = ",".join(retrieval.route.buckets)
    if not retrieval.results:
        answer_payload: dict[str, Any] = {
            "answer": NOT_FOUND_ANSWER,
            "citations": [],
            "buckets": retrieval.route.buckets,
        }
        save_cached_answer(
            db,
            standalone_question,
            cache_bucket,
            kb_version,
            answer_payload,
        )
        if standalone_question != question.strip():
            save_cached_answer(
                db,
                question,
                cache_bucket,
                kb_version,
                answer_payload,
            )
        return {**answer_payload, "cached": False}

    contexts = [
        (f"C{index}", chunk.text)
        for index, chunk in enumerate(retrieval.results, start=1)
    ]
    generated = generate_answer(standalone_question, contexts)
    if not generated["used_chunk_ids"]:
        generated["answer"] = NOT_FOUND_ANSWER
    citations = _citations(retrieval, generated["used_chunk_ids"])
    answer_payload = {
        "answer": generated["answer"],
        "citations": citations,
        "buckets": retrieval.route.buckets,
    }
    save_cached_answer(
        db,
        standalone_question,
        cache_bucket,
        kb_version,
        answer_payload,
    )
    if standalone_question != question.strip():
        save_cached_answer(
            db,
            question,
            cache_bucket,
            kb_version,
            answer_payload,
        )
    return {**answer_payload, "cached": False}


def recent_session_history(db: Session, session_id: int) -> list[dict[str, str]]:
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(6)
        .all()
    )
    return [
        {"role": message.role, "content": message.content}
        for message in reversed(messages)
    ]
