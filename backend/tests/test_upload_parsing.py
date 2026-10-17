from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import fitz
from docx import Document as DocxDocument

from app.auth import get_password_hash
from app.database import Base, get_db
from app.main import app
from app.models import User
from app.services.parser import parse_document

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

SQLALCHEMY_DATABASE_URL = "sqlite://"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def setup_users() -> None:
    app.dependency_overrides[get_db] = override_get_db
    db = TestingSessionLocal()
    try:
        db.query(User).delete()
        db.add(User(email="admin@company.com", password_hash=get_password_hash("admin123"), role="admin"))
        db.commit()
    finally:
        db.close()


def _create_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "HR Policy\n\nLeave Policy\n\nEmployees get 15 days")
    page = doc.new_page()
    page.insert_text((72, 72), "Security Policy\n\nUse MFA")
    doc.save(path)
    doc.close()


def test_parser_keeps_page_numbers() -> None:
    sample = Path("test_sample.pdf")
    _create_pdf(sample)
    try:
        records = parse_document(sample)
        assert len(records) == 2
        assert records[0]["page"] == 1
        assert "Leave Policy" in records[0]["text"]
        assert records[1]["page"] == 2
        assert "MFA" in records[1]["text"]
    finally:
        sample.unlink(missing_ok=True)


def test_admin_can_upload_pdf_and_get_page_count(monkeypatch) -> None:
    monkeypatch.setattr("app.routers.documents.index_document", lambda _document_id: None)
    setup_users()
    login = client.post("/auth/login", json={"email": "admin@company.com", "password": "admin123"})
    token = login.json()["access_token"]

    sample = Path("upload_test.pdf")
    _create_pdf(sample)
    try:
        file_bytes = sample.read_bytes()
        response = client.post(
            "/admin/documents",
            files={"file": ("sample.pdf", file_bytes, "application/pdf")},
            data={"bucket": "hr"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["page_count"] == 2
        assert payload["bucket"] == "hr"
        assert payload["filename"] == "sample.pdf"
        assert hashlib.sha256(file_bytes).hexdigest() == payload["file_hash"]
    finally:
        sample.unlink(missing_ok=True)
        stored_file = (
            Path(__file__).resolve().parents[1]
            / "uploads"
            / f"{hashlib.sha256(file_bytes).hexdigest()}.pdf"
        )
        stored_file.unlink(missing_ok=True)


def test_admin_rejects_invalid_docx_with_clear_error() -> None:
    setup_users()
    login = client.post(
        "/auth/login",
        json={"email": "admin@company.com", "password": "admin123"},
    )
    token = login.json()["access_token"]
    file_bytes = b"This file is not a valid DOCX archive."
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    response = client.post(
        "/admin/documents",
        files={"file": ("policy.docx", file_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"bucket": "hr"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "not a valid DOCX" in response.json()["detail"]
    assert not (
        Path(__file__).resolve().parents[1]
        / "uploads"
        / f"{file_hash}.docx"
    ).exists()


def test_admin_can_upload_valid_docx(monkeypatch) -> None:
    monkeypatch.setattr("app.routers.documents.index_document", lambda _document_id: None)
    setup_users()
    login = client.post(
        "/auth/login",
        json={"email": "admin@company.com", "password": "admin123"},
    )
    token = login.json()["access_token"]
    document = DocxDocument()
    document.add_paragraph("Employees receive 15 days of annual leave.")
    file_buffer = BytesIO()
    document.save(file_buffer)
    file_bytes = file_buffer.getvalue()
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    try:
        response = client.post(
            "/admin/documents",
            files={
                "file": (
                    "leave-policy.docx",
                    file_bytes,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
            data={"bucket": "hr"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200, response.text
        assert response.json()["filename"] == "leave-policy.docx"
    finally:
        (
            Path(__file__).resolve().parents[1]
            / "uploads"
            / f"{file_hash}.docx"
        ).unlink(missing_ok=True)


def test_admin_can_list_documents() -> None:
    setup_users()
    unauthenticated = client.get("/admin/documents")
    assert unauthenticated.status_code == 403

    login = client.post(
        "/auth/login",
        json={"email": "admin@company.com", "password": "admin123"},
    )
    token = login.json()["access_token"]
    response = client.get(
        "/admin/documents",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_debug_retrieve_is_admin_only(monkeypatch) -> None:
    setup_users()
    unauthenticated = client.post(
        "/admin/debug/retrieve",
        json={"question": "How many annual leave days?"},
    )
    assert unauthenticated.status_code == 403

    monkeypatch.setattr(
        "app.routers.documents.retrieve",
        lambda _question: SimpleNamespace(
            route=SimpleNamespace(buckets=["hr"], source="keyword"),
            results=[],
        ),
    )
    login = client.post(
        "/auth/login",
        json={"email": "admin@company.com", "password": "admin123"},
    )
    token = login.json()["access_token"]
    response = client.post(
        "/admin/debug/retrieve",
        json={"question": "How many annual leave days?"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "buckets": ["hr"],
        "route_source": "keyword",
        "results": [],
    }
