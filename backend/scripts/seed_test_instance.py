#!/usr/bin/env python3
"""
Seed a throwaway TEST instance: divisions, an admin, and one non-admin
test user, plus UVA DOM branding. Idempotent — safe to run on every boot.

Passwords come from the environment so nothing sensitive is committed:
    ADMIN_SEED_PASSWORD   (default "ChangeMe123!" for local dev)
    TEST_SEED_PASSWORD    (default "TestUser123!" for local dev)

On Fly these are set as secrets by deploy-test-fly.sh with random values.

Both accounts are created ready to log in (password_changed=True) so you
land straight in the app for security testing rather than a reset flow.

Usage:  python3 -m backend.scripts.seed_test_instance
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.models import Division, Faculty, InstanceConfig, SessionLocal, init_db
from backend.auth import hash_password

ADMIN_PW = os.getenv("ADMIN_SEED_PASSWORD", "ChangeMe123!")
TEST_PW = os.getenv("TEST_SEED_PASSWORD", "TestUser123!")

import json

# (key, label, color, method, cadence) — distinct policies so the test
# instance demonstrates the per-division scheduling settings out of the box.
DIVISIONS = [
    ("pccm", "PCCM", "#7c3aed", "priority", "annual"),
    ("micu_app", "MICU APPs", "#2563eb", "fcfs", "monthly"),
    ("hospitalist", "Hospitalists", "#059669", "wave", "quarterly"),
]


def _upsert_config(db, key, value):
    import json
    row = db.query(InstanceConfig).filter_by(key=key).first()
    encoded = json.dumps(value)
    if row:
        row.value = encoded
    else:
        db.add(InstanceConfig(key=key, value=encoded))


def main():
    init_db()  # ensure tables exist (fresh volume => full current schema)
    db = SessionLocal()
    try:
        # Divisions (with a starter self-scheduling policy each)
        for key, label, color, method, cadence in DIVISIONS:
            if not db.query(Division).filter_by(key=key).first():
                db.add(Division(
                    key=key, label=label, color=color,
                    scheduling_config=json.dumps({
                        "method": method, "cadence": cadence,
                        "self_scheduling_open": False, "notes": "",
                    }),
                ))
        db.commit()

        # Admin
        admin = db.query(Faculty).filter_by(id="ADMIN").first()
        if not admin:
            admin = Faculty(id="ADMIN", name="Administrator", email="admin@example.com",
                            is_admin=True, extra_config="{}")
            db.add(admin)
        admin.is_admin = True
        admin.password_hash = hash_password(ADMIN_PW)
        admin.password_changed = True
        admin.password_reset_required = False
        admin.registered = True
        admin.active = True
        admin.failed_login_attempts = 0
        admin.account_locked_until = None

        # Non-admin test user (a "test subject" in the MICU APP division)
        test = db.query(Faculty).filter_by(id="TESTER").first()
        if not test:
            test = Faculty(id="TESTER", name="Test Subject", email="tester@example.com",
                           is_admin=False, extra_config="{}")
            db.add(test)
        test.is_admin = False
        test.division_key = "micu_app"
        test.password_hash = hash_password(TEST_PW)
        test.password_changed = True
        test.password_reset_required = False
        test.registered = True
        test.active = True
        test.failed_login_attempts = 0
        test.account_locked_until = None

        # Branding + feature flags for the DOM instance
        _upsert_config(db, "group_name", "UVA DOM")
        _upsert_config(db, "org_name", "University of Virginia")
        _upsert_config(db, "app_name", "Faculty Hub")
        _upsert_config(db, "branding", {"org_label": "UVA DOM", "accent_color": None})
        feat_row = db.query(InstanceConfig).filter_by(key="features").first()
        import json
        feat = json.loads(feat_row.value) if feat_row else {}
        feat["messages"] = False
        feat.setdefault("knowledge_base", True)
        feat.setdefault("service_availability", True)
        _upsert_config(db, "features", feat)

        db.commit()
        print("Seeded test instance:")
        print(f"  admin : ADMIN  / (password from ADMIN_SEED_PASSWORD)")
        print(f"  user  : TESTER / (password from TEST_SEED_PASSWORD), division micu_app")
        print(f"  divisions: {', '.join(k for k, _, _ in DIVISIONS)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
