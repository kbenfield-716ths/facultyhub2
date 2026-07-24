#!/usr/bin/env python3
"""
unlock_faculty.py — FacultyHub emergency faculty unlock tool
============================================================
Clears all lockout conditions for a single faculty member so they can
log in and submit requests again.

Fixes ALL possible lock-out causes:
  • account_locked_until       — set after 5 failed login attempts
  • failed_login_attempts      — failure counter
  • active                     — account must be True to authenticate
  • registered                 — account must be True to be recognized
  • password_reset_required    — forces password change wall (optional reset)

Usage (on Fly.io):
    fly ssh console -a facultyhub
    cd /app
    python3 unlock_faculty.py

You will be prompted to enter the faculty member's email address or faculty ID.
"""

import sys
import os
from datetime import datetime

# ── locate the database ──────────────────────────────────────────────────────
DB_PATHS = [
    "/data/moonlighter.db",       # persistent volume (production)
    "./moonlighter.db",           # local fallback
    "/app/moonlighter.db",        # alternate app dir
]

def find_db():
    for p in DB_PATHS:
        if os.path.exists(p):
            return p
    return None

db_path = find_db()
if not db_path:
    print("ERROR: Could not find moonlighter.db in any expected location.")
    print("Searched:", DB_PATHS)
    sys.exit(1)

print(f"\n[DB] Using database: {db_path}\n")

# ── SQLAlchemy setup (mirrors backend/models.py) ─────────────────────────────
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = f"sqlite:///{db_path}"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
Session = sessionmaker(bind=engine)
Base = declarative_base()

# Minimal Faculty definition — only the fields we need
class Faculty(Base):
    __tablename__ = "faculty"
    id                     = Column(String, primary_key=True)
    name                   = Column(String, nullable=False)
    email                  = Column(String, unique=True, nullable=False)
    active                 = Column(Boolean, default=True)
    registered             = Column(Boolean, default=True)
    password_reset_required = Column(Boolean, default=False)
    failed_login_attempts  = Column(Integer, default=0)
    account_locked_until   = Column(DateTime, nullable=True)
    password_hash          = Column(String)

# ── helper ────────────────────────────────────────────────────────────────────
def find_faculty(db, identifier: str):
    """Find faculty by email OR faculty ID (case-insensitive)."""
    identifier = identifier.strip()
    # Try email first
    faculty = db.query(Faculty).filter(
        Faculty.email.ilike(identifier)
    ).first()
    if not faculty:
        # Try faculty ID (uppercase convention)
        faculty = db.query(Faculty).filter(
            Faculty.id == identifier.upper()
        ).first()
    return faculty

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  FacultyHub — Faculty Unlock Tool")
    print("=" * 60)

    identifier = input(
        "\nEnter the faculty member's EMAIL ADDRESS or FACULTY ID: "
    ).strip()

    if not identifier:
        print("No input provided. Exiting.")
        sys.exit(1)

    db = Session()
    try:
        faculty = find_faculty(db, identifier)

        if not faculty:
            print(f"\n❌  No faculty found matching: {identifier!r}")
            print("    Double-check the email or faculty ID and try again.")
            sys.exit(1)

        # ── show current state ────────────────────────────────────────────────
        print(f"\nFound faculty member:")
        print(f"  Name   : {faculty.name}")
        print(f"  ID     : {faculty.id}")
        print(f"  Email  : {faculty.email}")
        print(f"\nCurrent status:")
        print(f"  active                  : {faculty.active}")
        print(f"  registered              : {faculty.registered}")
        print(f"  failed_login_attempts   : {faculty.failed_login_attempts}")
        print(f"  account_locked_until    : {faculty.account_locked_until}")
        print(f"  password_reset_required : {faculty.password_reset_required}")
        print(f"  password_hash present   : {bool(faculty.password_hash)}")

        # ── confirm ───────────────────────────────────────────────────────────
        confirm = input(
            f"\nUnlock {faculty.name!r} and clear all lockout conditions? [yes/no]: "
        ).strip().lower()

        if confirm not in ("yes", "y"):
            print("Aborted — no changes made.")
            sys.exit(0)

        # ── apply fixes ───────────────────────────────────────────────────────
        changes = []

        if not faculty.active:
            faculty.active = True
            changes.append("active → True")

        if not faculty.registered:
            faculty.registered = True
            changes.append("registered → True")

        if faculty.failed_login_attempts != 0:
            faculty.failed_login_attempts = 0
            changes.append("failed_login_attempts → 0")

        if faculty.account_locked_until is not None:
            faculty.account_locked_until = None
            changes.append("account_locked_until → None (cleared)")

        if faculty.password_reset_required:
            faculty.password_reset_required = False
            changes.append("password_reset_required → False")

        if not changes:
            print("\n✅  No lockout conditions found — this account looks fine already.")
            print("    If they still can't log in, the issue is likely their password.")
            print("    You can reset it using the admin panel or rehash_standalone.py.")
        else:
            db.commit()
            print(f"\n✅  Done! Applied {len(changes)} fix(es):")
            for c in changes:
                print(f"    • {c}")
            print(f"\n    {faculty.name} should now be able to log in and submit requests.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
