from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Document
from app.services import indexing


def test_indexing_reuses_existing_embeddings_and_marks_indexed(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    with testing_session_local() as db:
        document = Document(
            filename="policy.txt",
            bucket="hr",
            file_hash="file-hash",
            status="uploaded",
            page_count=1,
        )
        db.add(document)
        db.commit()
        document_id = document.id

    known_text = "This existing policy content remains unchanged."
    new_text = "This is the changed policy content."
    known_hash = indexing.chunk_parsed_sections(
        [{"page": 1, "section": "Leave", "text": known_text}]
    )[0].chunk_hash
    existing_vector = [0.1, 0.2]
    added_vectors: list[list[float]] = []
    embedded_texts: list[str] = []

    class FakeCollection:
        pass

    def record_vectors(**kwargs) -> None:
        added_vectors.extend(kwargs["embeddings"])

    def embed(texts: list[str], batch_size: int) -> list[list[float]]:
        embedded_texts.extend(texts)
        return [[0.3, 0.4] for _ in texts]

    monkeypatch.setattr(indexing, "SessionLocal", testing_session_local)
    monkeypatch.setattr(
        indexing,
        "parse_document",
        lambda _path: [
            {"page": 1, "section": "Leave", "text": known_text},
            {"page": 1, "section": "Leave", "text": new_text},
        ],
    )
    monkeypatch.setattr(indexing, "get_collection", lambda: FakeCollection())
    monkeypatch.setattr(
        indexing,
        "get_existing_embeddings",
        lambda _collection, _hashes: {known_hash: existing_vector},
    )
    monkeypatch.setattr(indexing, "embed_documents", embed)
    monkeypatch.setattr(indexing, "add_document_chunks", record_vectors)

    try:
        indexing.index_document(document_id)

        assert embedded_texts == [new_text]
        assert added_vectors == [existing_vector, [0.3, 0.4]]
        with testing_session_local() as db:
            saved_document = db.get(Document, document_id)
            assert saved_document is not None
            assert saved_document.status == "indexed"
            assert len(saved_document.chunks) == 2
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
