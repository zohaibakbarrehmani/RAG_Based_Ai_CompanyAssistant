from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from functools import lru_cache
from typing import Any

from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 4


def _is_rate_limit_error(error: Exception) -> bool:
    response = getattr(error, "response", None)
    status_code = getattr(error, "code", None) or getattr(response, "status_code", None)
    return status_code == 429 or "429" in str(error)


def _call_with_rate_limit_retry(
    operation: Callable[[], Any],
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    for attempt in range(MAX_ATTEMPTS):
        try:
            return operation()
        except Exception as exc:
            if not _is_rate_limit_error(exc) or attempt == MAX_ATTEMPTS - 1:
                raise
            delay_seconds = 2**attempt
            logger.warning("Gemini embedding rate limited; retrying in %s seconds.", delay_seconds)
            sleep(delay_seconds)
    raise RuntimeError("Embedding request ended without a result.")


def embed_documents(
    texts: Sequence[str],
    batch_size: int | None = None,
) -> list[list[float]]:
    if not texts:
        return []
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY must be configured before indexing documents.")
    if not settings.gemini_embed_model:
        raise RuntimeError("GEMINI_EMBED_MODEL must be configured before indexing documents.")

    client = genai.Client(api_key=settings.gemini_api_key)
    size = batch_size or settings.embedding_batch_size
    if size < 1:
        raise ValueError("Embedding batch size must be positive.")

    vectors: list[list[float]] = []
    for offset in range(0, len(texts), size):
        batch = list(texts[offset : offset + size])
        response = _call_with_rate_limit_retry(
            lambda: client.models.embed_content(
                model=settings.gemini_embed_model,
                contents=batch,
                config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
            )
        )
        usage = getattr(response, "usage_metadata", None)
        logger.info(
            "Gemini document embedding token usage: prompt=%s total=%s.",
            getattr(usage, "prompt_token_count", None),
            getattr(usage, "total_token_count", None),
        )
        embeddings = response.embeddings or []
        if len(embeddings) != len(batch):
            raise RuntimeError("Gemini returned a different number of embeddings than inputs.")
        vectors.extend([list(item.values) for item in embeddings if item.values is not None])
        if len(vectors) < offset + len(batch):
            raise RuntimeError("Gemini returned an embedding without vector values.")
    return vectors


@lru_cache(maxsize=256)
def _cached_query_embedding(model_name: str, query: str) -> tuple[float, ...]:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY must be configured before retrieval.")
    client = genai.Client(api_key=settings.gemini_api_key)
    response = _call_with_rate_limit_retry(
        lambda: client.models.embed_content(
            model=model_name,
            contents=query,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
        )
    )
    usage = getattr(response, "usage_metadata", None)
    logger.info(
        "Gemini query embedding token usage: prompt=%s total=%s.",
        getattr(usage, "prompt_token_count", None),
        getattr(usage, "total_token_count", None),
    )
    embeddings = response.embeddings or []
    if len(embeddings) != 1 or embeddings[0].values is None:
        raise RuntimeError("Gemini did not return a query embedding.")
    return tuple(float(value) for value in embeddings[0].values)


def embed_query(query: str) -> list[float]:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY must be configured before retrieval.")
    if not settings.gemini_embed_model:
        raise RuntimeError("GEMINI_EMBED_MODEL must be configured before retrieval.")
    normalized_query = " ".join(query.split())
    if not normalized_query:
        raise ValueError("Query text must not be empty.")
    return list(_cached_query_embedding(settings.gemini_embed_model, normalized_query))
