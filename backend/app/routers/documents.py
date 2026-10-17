from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import AnswerCache, Chunk, Document, User
from app.schemas import (
    DebugRetrieveRequest,
    DebugRetrieveResponse,
    DocumentRead,
)
from app.services.indexing import index_document
from app.services.parser import MAX_FILE_SIZE_BYTES, SUPPORTED_EXTENSIONS, parse_document
from app.services.retriever import retrieve
from app.services.vector_store import delete_document_chunks, get_collection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])
VALID_BUCKETS = {"hr", "engineering", "product", "sop", "faq", "general"}


@router.get("/documents", response_model=list[DocumentRead])
def list_documents(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[DocumentRead]:
    documents = db.query(Document).order_by(Document.id.desc()).all()
    return documents


@router.post("/documents", response_model=DocumentRead)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    bucket: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> DocumentRead:
    normalized_bucket = bucket.strip().lower()
    if normalized_bucket not in VALID_BUCKETS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bucket must be one of: hr, engineering, product, sop, faq, general",
        )

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A filename is required.",
        )

    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty.",
        )

    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds 20 MB limit.",
        )

    extension = Path(file.filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF, DOCX, TXT and MD files are supported.",
        )

    file_hash = hashlib.sha256(contents).hexdigest()
    existing_document = db.query(Document).filter(Document.file_hash == file_hash).first()
    
    uploads_dir = Path(__file__).resolve().parents[2] / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{file_hash}{extension}"
    stored_path = uploads_dir / stored_name

    # If document exists and is failed, allow re-uploading and re-trying
    if existing_document is not None:
        if existing_document.status == "failed":
            stored_path.write_bytes(contents)
            existing_document.status = "indexing"
            existing_document.bucket = normalized_bucket
            existing_document.error_message = None
            db.commit()
            db.refresh(existing_document)
            background_tasks.add_task(index_document, existing_document.id)
            return existing_document
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This file already exists and is active in the knowledge base.",
            )

    stored_path.write_bytes(contents)

    try:
        parsed_sections = parse_document(stored_path)
    except ValueError as exc:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    page_count = max((item.get("page", 1) for item in parsed_sections), default=1)
    new_document = Document(
        filename=file.filename,
        bucket=normalized_bucket,
        file_hash=file_hash,
        status="uploaded",
        page_count=page_count,
        version=1,
        uploaded_by=current_user.id,
    )

    db.add(new_document)
    db.commit()
    db.refresh(new_document)
    background_tasks.add_task(index_document, new_document.id)

    return new_document


@router.post("/documents/{document_id}/reindex", response_model=DocumentRead)
def reindex_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> DocumentRead:
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} was not found.",
        )

    document.status = "indexing"
    document.error_message = None
    db.commit()
    db.refresh(document)

    background_tasks.add_task(index_document, document.id)
    return document


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> Response:
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} was not found.",
        )

    # 1. Remove physical file
    uploads_dir = Path(__file__).resolve().parents[2] / "uploads"
    stored_name = f"{document.file_hash}{Path(document.filename).suffix.lower()}"
    stored_path = uploads_dir / stored_name
    stored_path.unlink(missing_ok=True)

    # 2. Delete vectors from Chroma
    try:
        collection = get_collection()
        delete_document_chunks(collection, document.id)
    except Exception as exc:
        logger.warning("Could not delete chunks from vector store for document %s: %s", document_id, exc)

    # 3. Delete chunks & document from SQLite
    db.query(Chunk).filter(Chunk.document_id == document.id).delete()
    db.delete(document)
    # 4. Clear answer cache
    db.query(AnswerCache).delete()
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/debug/retrieve", response_model=DebugRetrieveResponse)
def debug_retrieve(
    payload: DebugRetrieveRequest,
    _: User = Depends(require_admin),
) -> DebugRetrieveResponse:
    if not payload.question.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question must not be empty.",
        )

    retrieval = retrieve(payload.question)
    return DebugRetrieveResponse(
        buckets=retrieval.route.buckets,
        route_source=retrieval.route.source,
        results=[
            {
                "document_id": chunk.document_id,
                "filename": chunk.filename,
                "bucket": chunk.bucket,
                "page": chunk.page,
                "section": chunk.section,
                "chunk_ids": chunk.chunk_ids,
                "text": chunk.text,
                "score": chunk.score,
                "token_estimate": chunk.token_estimate,
            }
            for chunk in retrieval.results
        ],
    )
