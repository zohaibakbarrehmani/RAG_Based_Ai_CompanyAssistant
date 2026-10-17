from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models import AnswerCache, Document

_CACHE_BUCKETS = (
    "hr",
    "engineering",
    "product",
    "sop",
    "faq",
    "general",
)
_CACHE_BUCKET_KEYS = (*_CACHE_BUCKETS, ",".join(_CACHE_BUCKETS))


def normalize_question(question: str) -> str:
    return re.sub(r"\s+", " ", question.strip().lower())


def get_kb_version(db: Session) -> int:
    """Return a stable version for the indexed document set."""
    documents = (
        db.query(Document.id, Document.file_hash, Document.version, Document.bucket)
        .filter(Document.status == "indexed")
        .order_by(Document.id)
        .all()
    )
    if not documents:
        return 0

    signature = json.dumps(
        [tuple(document) for document in documents],
        separators=(",", ":"),
    )
    return int(hashlib.sha256(signature.encode("utf-8")).hexdigest()[:15], 16)


def _question_hash(question: str, bucket: str) -> str:
    normalized = normalize_question(question)
    cache_key = f"{normalized}\0{bucket}"
    return hashlib.sha256(cache_key.encode("utf-8")).hexdigest()


def get_cached_answer(
    db: Session,
    question: str,
    kb_version: int,
) -> dict[str, Any] | None:
    cached = (
        db.query(AnswerCache)
        .filter(
            AnswerCache.question_hash.in_(
                [_question_hash(question, bucket) for bucket in _CACHE_BUCKET_KEYS]
            ),
            AnswerCache.kb_version == kb_version,
        )
        .order_by(AnswerCache.created_at.desc(), AnswerCache.id.desc())
        .first()
    )
    if cached is None:
        return None
    answer = json.loads(cached.answer_json)
    if not isinstance(answer, dict):
        raise ValueError("Cached answer is not a JSON object.")
    return answer


def save_cached_answer(
    db: Session,
    question: str,
    bucket: str,
    kb_version: int,
    answer: dict[str, Any],
) -> None:
    db.add(
        AnswerCache(
            question_hash=_question_hash(question, bucket),
            bucket=bucket,
            answer_json=json.dumps(answer, ensure_ascii=False),
            kb_version=kb_version,
        )
    )
    db.commit()
