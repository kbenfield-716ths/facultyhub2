#!/bin/sh
# Container entrypoint: seed the test instance (idempotent), then run the app.
# The SQLite DB lives on the mounted volume at /data/staff.db (see models.py).
set -e

echo "[entrypoint] Seeding test instance..."
python -m backend.scripts.seed_test_instance || {
    echo "[entrypoint] WARNING: seed failed; starting app anyway."
}

echo "[entrypoint] Starting uvicorn on :8080"
exec uvicorn backend.app:app --host 0.0.0.0 --port 8080
