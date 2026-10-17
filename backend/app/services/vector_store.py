from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb

VECTOR_DIRECTORY = Path(__file__).resolve().parents[2] / "chroma_db"
COLLECTION_NAME = "company_documents"


def get_collection() -> Any:
    client = chromadb.PersistentClient(path=str(VECTOR_DIRECTORY))
    return client.get_or_create_collection(name=COLLECTION_NAME)


def get_existing_embeddings(
    collection: Any,
    chunk_hashes: list[str],
) -> dict[str, list[float]]:
    if not chunk_hashes:
        return {}

    result = collection.get(
        where={"chunk_hash": {"$in": chunk_hashes}},
        include=["embeddings", "metadatas"],
    )
    existing: dict[str, list[float]] = {}
    metadatas = result["metadatas"] if result["metadatas"] is not None else []
    embeddings = result["embeddings"] if result["embeddings"] is not None else []
    for metadata, embedding in zip(metadatas, embeddings):
        if metadata is not None and embedding is not None:
            existing[str(metadata["chunk_hash"])] = list(embedding)
    return existing


def add_document_chunks(
    collection: Any,
    document_id: int,
    filename: str,
    bucket: str,
    chunks: list[Any],
    embeddings: list[list[float]],
    chunk_ids: list[int],
) -> None:
    if not chunks:
        return
    if not (len(chunks) == len(embeddings) == len(chunk_ids)):
        raise ValueError("Chunks, embeddings, and database IDs must have equal lengths.")

    collection.add(
        ids=[str(chunk_id) for chunk_id in chunk_ids],
        embeddings=embeddings,
        documents=[chunk.text for chunk in chunks],
        metadatas=[
            {
                "document_id": document_id,
                "filename": filename,
                "bucket": bucket,
                "page": chunk.page,
                "section": chunk.section,
                "chunk_id": chunk_id,
                "chunk_hash": chunk.chunk_hash,
            }
            for chunk_id, chunk in zip(chunk_ids, chunks)
        ],
    )


def delete_document_chunks(collection: Any, document_id: int) -> None:
    try:
        collection.delete(where={"document_id": document_id})
    except Exception:
        # Some versions of Chroma might need int or string match or might be empty
        try:
            collection.delete(where={"document_id": {"$eq": document_id}})
        except Exception:
            pass

