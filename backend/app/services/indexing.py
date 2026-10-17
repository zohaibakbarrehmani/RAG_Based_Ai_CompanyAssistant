from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import AnswerCache, Chunk, Document
from app.services.chunker import chunk_parsed_sections
from app.services.embeddings import embed_documents
from app.services.parser import parse_document
from app.services.vector_store import (
    add_document_chunks,
    delete_document_chunks,
    get_collection,
    get_existing_embeddings,
)

logger = logging.getLogger(__name__)


def index_document(document_id: int) -> None:
    db: Session = SessionLocal()
    document: Document | None = None
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if document is None:
            raise ValueError(f"Document {document_id} does not exist.")

        document.status = "indexing"
        document.error_message = None
        db.commit()

        upload_path = Path(__file__).resolve().parents[2] / "uploads"
        file_path = upload_path / f"{document.file_hash}{Path(document.filename).suffix.lower()}"
        parsed_sections = parse_document(file_path)
        chunks = chunk_parsed_sections(parsed_sections)

        if not chunks:
            # If document has empty text or only images
            document.status = "failed"
            document.error_message = "No extractable text found in this document. Please ensure the file contains readable text."
            db.commit()
            return

        collection = get_collection()

        # Clean up existing DB chunks and vector embeddings if re-indexing
        db.query(Chunk).filter(Chunk.document_id == document.id).delete()
        delete_document_chunks(collection, document.id)
        db.commit()

        existing_embeddings = get_existing_embeddings(
            collection,
            [chunk.chunk_hash for chunk in chunks],
        )
        chunks_by_hash = {chunk.chunk_hash: chunk for chunk in chunks}
        new_hashes = list(
            dict.fromkeys(
                chunk.chunk_hash
                for chunk in chunks
                if chunk.chunk_hash not in existing_embeddings
            )
        )
        
        if new_hashes:
            new_embeddings = embed_documents(
                [chunks_by_hash[chunk_hash].text for chunk_hash in new_hashes],
                batch_size=settings.embedding_batch_size,
            )
        else:
            new_embeddings = []

        embeddings_by_hash = dict(existing_embeddings)
        embeddings_by_hash.update(
            (chunk_hash, embedding)
            for chunk_hash, embedding in zip(new_hashes, new_embeddings)
        )

        db_chunks = [
            Chunk(
                document_id=document.id,
                chunk_hash=chunk.chunk_hash,
                page=chunk.page,
                section=chunk.section,
                text=chunk.text,
                token_estimate=chunk.token_estimate,
            )
            for chunk in chunks
        ]
        db.add_all(db_chunks)
        db.flush()

        add_document_chunks(
            collection=collection,
            document_id=document.id,
            filename=document.filename,
            bucket=document.bucket,
            chunks=chunks,
            embeddings=[embeddings_by_hash[chunk.chunk_hash] for chunk in chunks],
            chunk_ids=[chunk.id for chunk in db_chunks],
        )

        document.page_count = max((c.page for c in chunks), default=1)
        document.status = "indexed"
        document.error_message = None
        # Invalidate answer cache so new or updated documents immediately reflect in answers
        db.query(AnswerCache).delete()
        db.commit()

        logger.info(
            "Indexed document_id=%s (%s): %s chunks embedded, %s chunks reused.",
            document.id,
            document.filename,
            len(new_hashes),
            len(chunks) - len(new_hashes),
        )
    except Exception as exc:
        db.rollback()
        error_str = str(exc)
        if document is not None:
            document.status = "failed"
            document.error_message = error_str
            db.commit()
        logger.exception("Document indexing failed for document_id=%s: %s", document_id, error_str)
        raise
    finally:
        db.close()
