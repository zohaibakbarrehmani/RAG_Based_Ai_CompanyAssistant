import chromadb

from app.config import settings
from app.services import retriever
from app.services.router_bucket import BucketRoute


class FakeCollection:
    def __init__(self, result):
        self.result = result
        self.query_args = {}

    def query(self, **kwargs):
        self.query_args = kwargs
        return self.result


def _metadata(
    chunk_id: int,
    *,
    bucket: str = "hr",
    document_id: int = 1,
    page: int = 1,
    section: str = "Leave",
) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "filename": "policy.pdf",
        "bucket": bucket,
        "page": page,
        "section": section,
    }


def test_retrieval_filters_bucket_and_similarity_then_enforces_limits(monkeypatch) -> None:
    vectors = [[1.0, 0.0], [0.99, 0.1], [0.0, 1.0], [1.0, 0.0]]
    texts = [
        "Annual leave is available to employees.",
        "Annual leave is available to employees. Extra detail.",
        "A separate unrelated policy item.",
        "Annual leave details on a different page.",
    ]
    collection = FakeCollection(
        {
            "documents": [texts],
            "metadatas": [
                [
                    _metadata(1),
                    _metadata(2),
                    _metadata(3),
                    _metadata(4, page=2),
                ]
            ],
            "embeddings": [vectors],
        }
    )
    monkeypatch.setattr(
        retriever,
        "route_bucket",
        lambda _question: BucketRoute(buckets=["hr"], source="keyword"),
    )
    monkeypatch.setattr(retriever, "embed_query", lambda _question: [1.0, 0.0])
    monkeypatch.setattr(settings, "retrieval_top_k", 8)
    monkeypatch.setattr(settings, "retrieval_keep", 1)
    monkeypatch.setattr(settings, "min_similarity", 0.55)
    monkeypatch.setattr(settings, "max_context_tokens", 2000)

    response = retriever.retrieve("How many leave days?", collection=collection)

    assert response.route.buckets == ["hr"]
    assert collection.query_args["where"] == {"bucket": {"$in": ["hr"]}}
    assert collection.query_args["n_results"] == 8
    assert len(response.results) == 1
    assert response.results[0].chunk_ids == [1, 2]
    assert response.results[0].score > 0.99


def test_retrieval_returns_empty_when_nothing_meets_threshold(monkeypatch) -> None:
    collection = FakeCollection(
        {
            "documents": [["Different topic."]],
            "metadatas": [[_metadata(1)]],
            "embeddings": [[[0.0, 1.0]]],
        }
    )
    monkeypatch.setattr(
        retriever,
        "route_bucket",
        lambda _question: BucketRoute(buckets=["hr"], source="keyword"),
    )
    monkeypatch.setattr(retriever, "embed_query", lambda _question: [1.0, 0.0])
    monkeypatch.setattr(settings, "min_similarity", 0.55)

    response = retriever.retrieve("unrelated question", collection=collection)

    assert response.results == []


def test_retrieval_queries_real_chroma_with_bucket_filter(monkeypatch) -> None:
    collection = chromadb.EphemeralClient().get_or_create_collection(
        name="retriever_integration"
    )
    collection.add(
        ids=["21"],
        embeddings=[[1.0, 0.0]],
        documents=["The leave policy grants employees annual leave."],
        metadatas=[_metadata(21)],
    )
    monkeypatch.setattr(
        retriever,
        "route_bucket",
        lambda _question: BucketRoute(buckets=["hr"], source="keyword"),
    )
    monkeypatch.setattr(retriever, "embed_query", lambda _question: [1.0, 0.0])
    monkeypatch.setattr(settings, "min_similarity", 0.55)

    response = retriever.retrieve("annual leave", collection=collection)

    assert len(response.results) == 1
    assert response.results[0].filename == "policy.pdf"
    assert response.results[0].bucket == "hr"
    assert response.results[0].score == 1.0
