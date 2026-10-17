import chromadb

from app.services.chunker import chunk_parsed_sections
from app.services.vector_store import add_document_chunks, get_existing_embeddings


def test_chroma_stores_citation_metadata_and_reuses_embedding(tmp_path) -> None:
    client = chromadb.PersistentClient(path=str(tmp_path))
    collection = client.get_or_create_collection(name="test_documents")
    chunks = chunk_parsed_sections(
        [{"page": 2, "section": "Benefits", "text": "Employees receive annual leave."}]
    )
    original_embedding = [0.1, 0.2, 0.3]

    add_document_chunks(
        collection=collection,
        document_id=4,
        filename="handbook.pdf",
        bucket="hr",
        chunks=chunks,
        embeddings=[original_embedding],
        chunk_ids=[40],
    )

    reused = get_existing_embeddings(collection, [chunks[0].chunk_hash])
    actual_embedding = reused[chunks[0].chunk_hash]
    assert all(
        abs(actual - expected) < 1e-5
        for actual, expected in zip(actual_embedding, original_embedding)
    )

    result = collection.get(ids=["40"], include=["metadatas"])
    metadata = result["metadatas"][0]
    assert metadata["document_id"] == 4
    assert metadata["filename"] == "handbook.pdf"
    assert metadata["bucket"] == "hr"
    assert metadata["page"] == 2
    assert metadata["section"] == "Benefits"
    assert metadata["chunk_id"] == 40
