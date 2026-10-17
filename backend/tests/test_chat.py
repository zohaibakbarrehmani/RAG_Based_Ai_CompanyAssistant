from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
from app.database import Base, get_db
from app.main import app
from app.models import User


@pytest.fixture
def chat_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with session_factory() as db:
        db.add_all(
            [
                User(
                    email="chat-employee@company.com",
                    password_hash=get_password_hash("employee-password"),
                    role="employee",
                ),
                User(
                    email="other-employee@company.com",
                    password_hash=get_password_hash("other-password"),
                    role="employee",
                ),
            ]
        )
        db.commit()

    yield TestClient(app), session_factory
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _login(client: TestClient, email: str, password: str) -> str:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_chat_ask_persists_messages_and_citations(chat_client, monkeypatch) -> None:
    client, session_factory = chat_client
    token = _login(client, "chat-employee@company.com", "employee-password")
    monkeypatch.setattr(
        "app.routers.chat.answer_question",
        lambda _db, _question, _history: {
            "answer": "Employees receive 15 days.",
            "citations": [
                {
                    "filename": "leave.pdf",
                    "page": 2,
                    "section": "Annual Leave",
                    "snippet": "Employees receive 15 days.",
                }
            ],
            "cached": False,
        },
    )

    response = client.post(
        "/chat/ask",
        json={"question": "How many annual leave days?"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] > 0
    assert payload["citations"][0]["page"] == 2

    detail = client.get(
        f"/chat/sessions/{payload['session_id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail.status_code == 200
    messages = detail.json()["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[1]["citations"] == payload["citations"]


def test_chat_sessions_are_private_to_owner(chat_client) -> None:
    client, _session_factory = chat_client
    owner_token = _login(client, "chat-employee@company.com", "employee-password")
    other_token = _login(client, "other-employee@company.com", "other-password")
    create = client.post(
        "/chat/sessions",
        json={"title": "My private session"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    session_id = create.json()["id"]

    denied = client.get(
        f"/chat/sessions/{session_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )

    assert denied.status_code == 404


def test_chat_sessions_can_be_pinned_and_deleted(chat_client) -> None:
    client, _session_factory = chat_client
    token = _login(client, "chat-employee@company.com", "employee-password")
    create = client.post(
        "/chat/sessions",
        json={"title": "Policy questions"},
        headers={"Authorization": f"Bearer {token}"},
    )
    session_id = create.json()["id"]

    pinned = client.patch(
        f"/chat/sessions/{session_id}",
        json={"pinned": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert pinned.status_code == 200
    assert pinned.json()["pinned"] is True
    assert client.get(
        "/chat/sessions",
        headers={"Authorization": f"Bearer {token}"},
    ).json()[0]["pinned"] is True

    deleted = client.delete(
        f"/chat/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert deleted.status_code == 204
    assert client.get(
        f"/chat/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token}"},
    ).status_code == 404
