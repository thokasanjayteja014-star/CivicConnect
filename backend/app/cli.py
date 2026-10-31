"""Operator CLI.

  python -m app.cli create-admin --email you@example.org --name "Your Name"
  python -m app.cli bootstrap-admin-from-env   # for hosts without a shell (e.g. Render free)
  python -m app.cli generate-vapid-keys        # keys for browser push notifications

Creates a real SYSTEM_ADMIN account (password prompted, never echoed or
logged). This is the only bootstrap step; all other records - departments,
jurisdictions, officers, complaints - are created through the application.
"""
import argparse
import base64
import getpass
import os
import sys

from sqlalchemy import func, select

from app import audit
from app.core.db import SessionLocal
from app.models import User
from app.models.enums import AccountStatus, Role
from app.security import hash_password


def create_admin(email: str, name: str, password: str | None) -> None:
    password = password or getpass.getpass("Password (min 12 chars): ")
    if len(password) < 12:
        sys.exit("Password must be at least 12 characters.")
    db = SessionLocal()
    try:
        if db.scalar(select(User.id).where(func.lower(User.email) == email.lower())):
            sys.exit("A user with this email already exists.")
        u = User(full_name=name, email=email.lower(), password_hash=hash_password(password), role=Role.SYSTEM_ADMIN,
                 account_status=AccountStatus.ACTIVE)
        db.add(u)
        db.flush()
        audit.record(db, actor_id=None, actor_label="system:cli", action="ADMIN_BOOTSTRAPPED", entity_type="user", entity_id=u.id)
        db.commit()
        print(f"System administrator created: {email}")
    finally:
        db.close()


def bootstrap_admin_from_env() -> None:
    """Create the first SYSTEM_ADMIN from BOOTSTRAP_ADMIN_EMAIL / _NAME / _PASSWORD if no admin exists yet.
    Does nothing when the variables are unset. Remove the variables after the first deploy."""
    email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "").strip()
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
    if not email or not password:
        return
    db = SessionLocal()
    try:
        if db.scalar(select(User.id).where(User.role == Role.SYSTEM_ADMIN).limit(1)):
            print("bootstrap-admin: an administrator already exists; nothing to do.")
            return
    finally:
        db.close()
    try:
        create_admin(email, os.environ.get("BOOTSTRAP_ADMIN_NAME", "Administrator").strip() or "Administrator", password)
    except SystemExit as exc:  # never block the server from starting
        print(f"bootstrap-admin: skipped ({exc})")


def generate_vapid_keys() -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    raw_private = key.private_numbers().private_value.to_bytes(32, "big")
    raw_public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
    print(f"VAPID_PUBLIC_KEY={b64(raw_public)}")
    print(f"VAPID_PRIVATE_KEY={b64(raw_private)}")
    print("VAPID_SUBJECT=mailto:you@example.org")


def main() -> None:
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-admin")
    c.add_argument("--email", required=True)
    c.add_argument("--name", required=True)
    c.add_argument("--password-stdin", action="store_true", help="Read the password from stdin (for automation)")
    sub.add_parser("bootstrap-admin-from-env")
    sub.add_parser("generate-vapid-keys")
    args = p.parse_args()
    if args.cmd == "create-admin":
        create_admin(args.email, args.name, sys.stdin.readline().strip() if args.password_stdin else None)
    elif args.cmd == "bootstrap-admin-from-env":
        bootstrap_admin_from_env()
    elif args.cmd == "generate-vapid-keys":
        generate_vapid_keys()


if __name__ == "__main__":
    main()
