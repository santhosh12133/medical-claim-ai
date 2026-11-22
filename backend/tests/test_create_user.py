"""scripts/create_user.py: real accounts for servers (runs where SQLAlchemy is installed, e.g. CI)."""

import tempfile
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import models  # noqa: E402,F401
from auth import verify_password  # noqa: E402
from database import Base  # noqa: E402
from models_user import User  # noqa: E402
from scripts.create_user import create_or_reset  # noqa: E402


@pytest.fixture()
def factory():
    engine = create_engine(f"sqlite:///{Path(tempfile.mkdtemp()) / 'users.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def stored(factory, email):
    with factory() as db:
        return db.query(User).filter(User.email == email).one()


def test_generated_password_works_and_is_returned_once(factory, monkeypatch):
    monkeypatch.delenv("MCA_PASSWORD", raising=False)
    action, password = create_or_reset(" Owner@Example.com ", "Owner", "admin", False, "MCA_PASSWORD", factory)
    assert action == "created (admin)" and len(password) >= 16
    user = stored(factory, "owner@example.com")
    assert user.role == "admin" and verify_password(password, user.password_hash, user.password_salt)


def test_supplied_password_and_reset(factory, monkeypatch):
    monkeypatch.setenv("MCA_PASSWORD", "correct horse battery")
    assert create_or_reset("e@x.com", "E", "employee", False, "MCA_PASSWORD", factory) == ("created (employee)", None)
    monkeypatch.setenv("MCA_PASSWORD", "another long password")
    assert create_or_reset("e@x.com", None, None, True, "MCA_PASSWORD", factory) == ("password reset", None)
    user = stored(factory, "e@x.com")
    assert verify_password("another long password", user.password_hash, user.password_salt)


def test_refuses_duplicates_short_passwords_and_bad_roles(factory, monkeypatch):
    monkeypatch.setenv("MCA_PASSWORD", "long enough password")
    create_or_reset("a@x.com", "A", "admin", False, "MCA_PASSWORD", factory)
    with pytest.raises(SystemExit, match="already exists"):
        create_or_reset("a@x.com", "A", "admin", False, "MCA_PASSWORD", factory)
    with pytest.raises(SystemExit, match="required"):
        create_or_reset("b@x.com", "B", "superuser", False, "MCA_PASSWORD", factory)
    with pytest.raises(SystemExit, match="does not exist"):
        create_or_reset("c@x.com", None, None, True, "MCA_PASSWORD", factory)
    monkeypatch.setenv("MCA_PASSWORD", "short")
    with pytest.raises(SystemExit, match="at least 12"):
        create_or_reset("d@x.com", "D", "employee", False, "MCA_PASSWORD", factory)
