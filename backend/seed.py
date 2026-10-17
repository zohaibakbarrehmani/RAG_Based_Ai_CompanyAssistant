from app.auth import get_password_hash
from app.database import SessionLocal, Base, engine
from app.models import User


def seed_users() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == "admin@company.com").first()
        employee = db.query(User).filter(User.email == "employee@company.com").first()

        if admin is None:
            db.add(
                User(
                    email="admin@company.com",
                    password_hash=get_password_hash("admin123"),
                    role="admin",
                )
            )

        if employee is None:
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


if __name__ == "__main__":
    seed_users()
    print("Seed users created.")
