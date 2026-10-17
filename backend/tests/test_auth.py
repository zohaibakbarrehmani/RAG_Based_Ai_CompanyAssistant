from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
from app.database import Base, get_db
from app.main import app
from app.models import User

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
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        db.query(User).delete()
        db.add(
            User(
                email="admin@company.com",
                password_hash=get_password_hash("admin123"),
                role="admin",
            )
        )
        db.add(
            User(
                email="employee@company.com",
                password_hash=get_password_hash("employee123"),
                role="employee",
            )
        )
        db.commit()
    finally:
        db.close()


def test_employee_cannot_access_admin_route() -> None:
    setup_users()
    login_response = client.post(
        "/auth/login",
        json={"email": "employee@company.com", "password": "employee123"},
    )
    token = login_response.json()["access_token"]

    admin_response = client.get(
        "/admin/health",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert admin_response.status_code == 403
    assert admin_response.json()["detail"] == "Admin access required"


def test_admin_can_access_admin_route() -> None:
    setup_users()
    login_response = client.post(
        "/auth/login",
        json={"email": "admin@company.com", "password": "admin123"},
    )
    token = login_response.json()["access_token"]

    admin_response = client.get(
        "/admin/health",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert admin_response.status_code == 200
    assert admin_response.json()["status"] == "ok"
