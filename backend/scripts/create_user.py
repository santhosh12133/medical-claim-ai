"""Create (or reset the password of) a real user account. Use this instead of seed_demo_users.py on a server.

    python scripts/create_user.py --email you@example.com --name "Your Name" --role admin
    MCA_PASSWORD='a long password' python scripts/create_user.py --email a@b.com --name A --role employee
    python scripts/create_user.py --email you@example.com --reset-password

The password comes from the environment variable named by --password-env (default MCA_PASSWORD), so it
never appears in the shell history or process list. If that variable is unset a random password is
generated and printed once.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import select  # noqa: E402

import models  # noqa: E402,F401  (registers every table)
from auth import hash_password  # noqa: E402
from database import SessionLocal  # noqa: E402
from models_user import User  # noqa: E402

ROLES = ("admin", "employee")
MIN_PASSWORD_LENGTH = 12


def resolve_password(env_name: str) -> tuple[str, bool]:
    supplied = os.getenv(env_name)
    if supplied:
        if len(supplied) < MIN_PASSWORD_LENGTH:
            raise SystemExit(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
        return supplied, False
    return secrets.token_urlsafe(15), True


def create_or_reset(email: str, name: str | None, role: str | None, reset_password: bool, env_name: str,
                    session_factory=SessionLocal) -> tuple[str, str | None]:
    """Returns (action, generated_password_or_None)."""
    email = email.strip().lower()
    if "@" not in email:
        raise SystemExit("Enter a valid e-mail address")
    with session_factory() as db:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user and not reset_password:
            raise SystemExit(f"{email} already exists (role {user.role}); use --reset-password to change its password")
        if not user and reset_password:
            raise SystemExit(f"{email} does not exist")
        if not user and (not name or role not in ROLES):
            raise SystemExit(f"--name and --role ({' or '.join(ROLES)}) are required for a new account")
        password, generated = resolve_password(env_name)
        password_hash, password_salt = hash_password(password)
        if user:
            user.password_hash, user.password_salt = password_hash, password_salt
            action = "password reset"
        else:
            db.add(User(full_name=name.strip(), email=email, role=role, password_hash=password_hash,
                        password_salt=password_salt))
            action = f"created ({role})"
        db.commit()
    return action, password if generated else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name")
    parser.add_argument("--role", choices=ROLES)
    parser.add_argument("--reset-password", action="store_true")
    parser.add_argument("--password-env", default="MCA_PASSWORD")
    args = parser.parse_args()
    action, generated = create_or_reset(args.email, args.name, args.role, args.reset_password, args.password_env)
    print(f"{args.email.strip().lower()}: {action}")
    if generated:
        print(f"Generated password (shown once, store it safely): {generated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
