from pathlib import Path
import sys

from sqlalchemy import select

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from auth import hash_password
from database import SessionLocal
from models_user import User


DEMO_USERS = [
    {"full_name": "Employee Demo", "email": "employee@demo.com", "role": "employee", "password": "employee123"},
    {"full_name": "Admin Demo", "email": "admin@demo.com", "role": "admin", "password": "admin123"},
]


def seed_demo_users() -> None:
    db = SessionLocal()
    try:
        for demo_user in DEMO_USERS:
            existing_user = db.execute(select(User).where(User.email == demo_user["email"])).scalar_one_or_none()
            if existing_user:
                continue

            password_hash, password_salt = hash_password(demo_user["password"])
            db.add(
                User(
                    full_name=demo_user["full_name"],
                    email=demo_user["email"],
                    role=demo_user["role"],
                    password_hash=password_hash,
                    password_salt=password_salt,
                )
            )

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed_demo_users()