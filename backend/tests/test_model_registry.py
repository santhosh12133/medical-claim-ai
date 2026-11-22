"""Regression: every process that imports the Claim model must be able to flush it.

The worker container imports ``models`` but not ``models_user``; before the fix SQLAlchemy could not
resolve ``claims.user_id`` / ``claims.reviewed_by`` -> ``users.id`` and the worker crash-looped.
The check runs in a fresh interpreter so imports made by other tests cannot hide the problem.
"""

import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")

BACKEND = Path(__file__).resolve().parents[1]

WORKER_IMPORTS = """
import os, tempfile
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "registry.db")
os.environ.setdefault("SECRET_KEY", "registry-test-secret-key-0123456789abcdef")
from database import Base, SessionLocal, engine
from models import Claim          # exactly what scripts/claim_worker.py imports
import rag.db.models  # noqa: F401
assert "users" in Base.metadata.tables, "users table not registered"
Base.metadata.create_all(engine)
with SessionLocal() as db:
    db.add(Claim(employee_name="Registry Test", status="Processing", file_path="x", processing_status="queued"))
    db.commit()
print("ok")
"""


def test_claim_model_flushes_without_importing_user_model_explicitly():
    result = subprocess.run([sys.executable, "-c", WORKER_IMPORTS], cwd=BACKEND, capture_output=True, text=True,
                            timeout=120)
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip().endswith("ok")
