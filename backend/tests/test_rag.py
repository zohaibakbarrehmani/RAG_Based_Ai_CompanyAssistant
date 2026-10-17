from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Document
from app.services import rag
from app.services.router_bucket import BucketRoute


def _database():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    return engine, session_factory


def test_repeated_question_uses_cache_without_retrieval_or_generation(monkeypatch) -> None:
    engine, session_factory = _database()
    with session_factory() as db:
        db.add(
            Document(
                filename="leave.pdf",
                bucket="hr",
                file_hash="current-file",
                status="indexed",
                page_count=1,
                version=1,
            )
        )
        db.commit()
        retrieval_calls = 0
        generation_calls = 0

        def retrieve(_question):
            nonlocal retrieval_calls
            retrieval_calls += 1
            return SimpleNamespace(
                route=BucketRoute(buckets=["hr"], source="keyword"),
                results=[
                    SimpleNamespace(
                        filename="leave.pdf",
                        page=2,
                        section="Annual Leave",
                        text="Employees receive 15 days of annual leave.",
                    )
                ],
            )

        def generate(_question, _contexts):
            nonlocal generation_calls
            generation_calls += 1
            return {"answer": "Employees receive 15 days.", "used_chunk_ids": ["C1"]}

        monkeypatch.setattr(rag, "retrieve", retrieve)
        monkeypatch.setattr(rag, "generate_answer", generate)

        first = rag.answer_question(db, "  How many annual leave days?  ")
        second = rag.answer_question(db, "how many annual leave days?")

        assert first["cached"] is False
        assert second["cached"] is True
        assert second["answer"] == "Employees receive 15 days."
        assert second["citations"] == [
            {
                "filename": "leave.pdf",
                "page": 2,
                "section": "Annual Leave",
                "snippet": "Employees receive 15 days of annual leave.",
            }
        ]
        assert retrieval_calls == 1
        assert generation_calls == 1
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_empty_retrieval_returns_not_found_without_generation(monkeypatch) -> None:
    engine, session_factory = _database()
    with session_factory() as db:
        monkeypatch.setattr(
            rag,
            "retrieve",
            lambda _question: SimpleNamespace(
                route=BucketRoute(buckets=["general"], source="keyword"),
                results=[],
            ),
        )

        def unexpected_generation(*_args):
            raise AssertionError("No-answer retrieval must not call the LLM.")

        monkeypatch.setattr(rag, "generate_answer", unexpected_generation)
        result = rag.answer_question(db, "How to administer a moon base?")

        assert result["answer"] == "I couldn't find this in the company documents."
        assert result["citations"] == []
        assert result["cached"] is False
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_answer_without_cited_context_is_replaced_with_not_found(monkeypatch) -> None:
    engine, session_factory = _database()
    with session_factory() as db:
        monkeypatch.setattr(
            rag,
            "retrieve",
            lambda _question: SimpleNamespace(
                route=BucketRoute(buckets=["hr"], source="keyword"),
                results=[
                    SimpleNamespace(
                        filename="policy.pdf",
                        page=1,
                        section="Policy",
                        text="Only this retrieved text is available.",
                    )
                ],
            ),
        )
        monkeypatch.setattr(
            rag,
            "generate_answer",
            lambda _question, _contexts: {
                "answer": "An unsupported generated claim.",
                "used_chunk_ids": [],
            },
        )

        result = rag.answer_question(db, "What does the policy say?")

        assert result["answer"] == "I couldn't find this in the company documents."
        assert result["citations"] == []
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_indexed_document_changes_cache_version(monkeypatch) -> None:
    engine, session_factory = _database()
    with session_factory() as db:
        monkeypatch.setattr(
            rag,
            "retrieve",
            lambda _question: SimpleNamespace(
                route=BucketRoute(buckets=["hr"], source="keyword"),
                results=[SimpleNamespace(
                    filename="policy.pdf",
                    page=1,
                    section="Policy",
                    text="The policy answer.",
                )],
            ),
        )
        generation_calls = 0

        def generate(_question, _contexts):
            nonlocal generation_calls
            generation_calls += 1
            return {"answer": "Policy answer.", "used_chunk_ids": ["C1"]}

        monkeypatch.setattr(rag, "generate_answer", generate)
        db.add(
            Document(
                filename="first.pdf",
                bucket="hr",
                file_hash="first",
                status="indexed",
                page_count=1,
                version=1,
            )
        )
        db.commit()
        rag.answer_question(db, "What is the policy?")
        db.add(
            Document(
                filename="second.pdf",
                bucket="hr",
                file_hash="second",
                status="indexed",
                page_count=1,
                version=1,
            )
        )
        db.commit()
        result = rag.answer_question(db, "What is the policy?")

        assert result["cached"] is False
        assert generation_calls == 2
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
