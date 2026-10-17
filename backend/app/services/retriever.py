from __future__ import annotations

import re
from dataclasses import dataclass
from math import sqrt
from typing import Any

from app.config import settings
from app.services.embeddings import embed_query
from app.services.router_bucket import BUCKETS, BucketRoute, route_bucket
from app.services.vector_store import get_collection


@dataclass
class RetrievedChunk:
    document_id: int
    filename: str
    bucket: str
    page: int
    section: str
    chunk_ids: list[int]
    text: str
    score: float
    token_estimate: int


@dataclass
class RetrievalResponse:
    route: BucketRoute
    results: list[RetrievedChunk]


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text.split()) * 4 + 2) // 3)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Query and stored embeddings have different dimensions.")
    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


def _as_int(value: Any, key: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Retrieved chunk is missing valid {key} metadata.") from exc


def _remove_overlap(left_text: str, right_text: str) -> str:
    left_words = left_text.split()
    right_words = right_text.split()
    max_overlap = min(len(left_words), len(right_words), 80)
    for overlap in range(max_overlap, 0, -1):
        if left_words[-overlap:] == right_words[:overlap]:
            return " ".join(left_words + right_words[overlap:])
    return f"{left_text} {right_text}"


def _merge_adjacent(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    ordered = sorted(
        chunks,
        key=lambda chunk: (
            chunk.document_id,
            chunk.page,
            chunk.section,
            chunk.chunk_ids[0],
        ),
    )
    merged: list[RetrievedChunk] = []
    for chunk in ordered:
        previous = merged[-1] if merged else None
        if (
            previous is not None
            and previous.document_id == chunk.document_id
            and previous.page == chunk.page
            and previous.section == chunk.section
            and previous.chunk_ids[-1] + 1 == chunk.chunk_ids[0]
        ):
            previous.text = _remove_overlap(previous.text, chunk.text)
            previous.chunk_ids.extend(chunk.chunk_ids)
            previous.score = max(previous.score, chunk.score)
            previous.token_estimate = _estimate_tokens(previous.text)
        else:
            merged.append(chunk)
    return merged


def _is_near_duplicate(candidate: RetrievedChunk, selected: list[RetrievedChunk]) -> bool:
    candidate_words = set(re.findall(r"[a-z0-9]+", candidate.text.lower()))
    if not candidate_words:
        return False
    for existing in selected:
        existing_words = set(re.findall(r"[a-z0-9]+", existing.text.lower()))
        if not existing_words:
            continue
        overlap = len(candidate_words & existing_words)
        # Use 0.82 — tight enough to remove true duplicates but distinct
        # enough that related-but-different sections both make it through
        similarity = overlap / min(len(candidate_words), len(existing_words))
        if similarity >= 0.82:
            return True
    return False


def _to_chunk(metadata: dict[str, Any], text: str, score: float) -> RetrievedChunk:
    chunk_id = _as_int(metadata.get("chunk_id"), "chunk_id")
    return RetrievedChunk(
        document_id=_as_int(metadata.get("document_id"), "document_id"),
        filename=str(metadata.get("filename", "")),
        bucket=str(metadata.get("bucket", "")),
        page=_as_int(metadata.get("page"), "page"),
        section=str(metadata.get("section") or "General"),
        chunk_ids=[chunk_id],
        text=text,
        score=score,
        token_estimate=_estimate_tokens(text),
    )


def retrieve(question: str, collection: Any | None = None) -> RetrievalResponse:
    route = route_bucket(question)
    query_embedding = embed_query(question)
    vector_collection = collection or get_collection()
    
    where_filter = {"bucket": {"$in": route.buckets}} if route.buckets else None
    try:
        result = vector_collection.query(
            query_embeddings=[query_embedding],
            n_results=max(1, settings.retrieval_top_k),
            where=where_filter,
            include=["documents", "metadatas", "embeddings"],
        )
    except Exception:
        result = {"documents": [], "metadatas": [], "embeddings": []}

    documents = result["documents"][0] if result.get("documents") else []
    metadatas = result["metadatas"][0] if result.get("metadatas") else []
    embeddings = result["embeddings"][0] if result.get("embeddings") else []
    
    candidates: list[RetrievedChunk] = []
    for text, metadata, embedding in zip(documents, metadatas, embeddings):
        if text is None or metadata is None or embedding is None:
            continue
        score = _cosine_similarity(query_embedding, list(embedding))
        if score >= settings.min_similarity:
            candidates.append(_to_chunk(metadata, text, score))

    # Fallback to query all documents if specific bucket filter yielded no relevant chunks
    if not candidates and where_filter is not None:
        try:
            fallback_result = vector_collection.query(
                query_embeddings=[query_embedding],
                n_results=max(1, settings.retrieval_top_k),
                include=["documents", "metadatas", "embeddings"],
            )
            fb_documents = fallback_result["documents"][0] if fallback_result.get("documents") else []
            fb_metadatas = fallback_result["metadatas"][0] if fallback_result.get("metadatas") else []
            fb_embeddings = fallback_result["embeddings"][0] if fallback_result.get("embeddings") else []
            for text, metadata, embedding in zip(fb_documents, fb_metadatas, fb_embeddings):
                if text is None or metadata is None or embedding is None:
                    continue
                score = _cosine_similarity(query_embedding, list(embedding))
                if score >= settings.min_similarity:
                    candidates.append(_to_chunk(metadata, text, score))
        except Exception:
            pass

    candidates = _merge_adjacent(candidates)
    candidates.sort(key=lambda chunk: chunk.score, reverse=True)

    kept: list[RetrievedChunk] = []
    used_tokens = 0
    for chunk in candidates:
        if len(kept) >= max(1, settings.retrieval_keep):
            break
        if _is_near_duplicate(chunk, kept):
            continue
        if used_tokens + chunk.token_estimate > settings.max_context_tokens:
            break  # budget exhausted — stop rather than skipping to find smaller chunks
        kept.append(chunk)
        used_tokens += chunk.token_estimate

    return RetrievalResponse(route=route, results=kept)
