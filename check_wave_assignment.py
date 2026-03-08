#!/usr/bin/env python3
"""
check_wave_assignment.py — Diagnose why a faculty member is on the traditional
submission path instead of the wave draft path.

Usage (on Fly.io):
    fly ssh console -a facultyhub
    cd /app
    python3 check_wave_assignment.py
"""

import os, sys
from datetime import datetime

DB_PATHS = ["/data/moonlighter.db", "./moonlighter.db", "/app/moonlighter.db"]

def find_db():
    for p in DB_PATHS:
        if os.path.exists(p):
            return p

db_path = find_db()
if not db_path:
    print("ERROR: Could not find database."); sys.exit(1)

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
DB = sessionmaker(bind=engine)()

identifier = input("Enter faculty email or ID: ").strip()

# ── find faculty ──────────────────────────────────────────────────────────────
row = DB.execute(text(
    "SELECT id, name, email, active FROM faculty WHERE email = :v OR id = :v2"
), {"v": identifier, "v2": identifier.upper()}).fetchone()

if not row:
    print(f"\n❌  No faculty found for: {identifier!r}"); sys.exit(1)

fid, fname, femail, factive = row
print(f"\nFaculty : {fname}  ({fid})  active={factive}")

# ── active draft config ───────────────────────────────────────────────────────
config = DB.execute(text(
    "SELECT id, year, status, close_date FROM draft_wave_configs WHERE status='active'"
)).fetchone()

if not config:
    print("\n⚠️  No active wave draft config found — faculty will always use the traditional path.")
    sys.exit(0)

cfg_id, cfg_year, cfg_status, cfg_close = config
now = datetime.utcnow()
print(f"\nDraft config: year={cfg_year}  status={cfg_status}  closes={cfg_close}  (now UTC={now})")
print(f"  Draft closed? {cfg_close <= str(now)}")

# ── wave assignment ───────────────────────────────────────────────────────────
assignment = DB.execute(text("""
    SELECT wfa.id, dw.name, dw.open_date, wfa.notified_at, wfa.reminder_sent_at
    FROM wave_faculty_assignments wfa
    JOIN draft_waves dw ON dw.id = wfa.wave_id
    WHERE wfa.faculty_id = :fid AND dw.config_id = :cfg_id
"""), {"fid": fid, "cfg_id": cfg_id}).fetchone()

if not assignment:
    print(f"\n❌  PROBLEM: {fname} has NO wave assignment for the active config.")
    print("   Fix: Add them to a wave in the admin panel → Draft Waves.")
    sys.exit(0)

asgn_id, wave_name, open_date, notified_at, reminder_sent_at = assignment
print(f"\nWave assignment found:")
print(f"  Wave        : {wave_name}")
print(f"  open_date   : {open_date}  (UTC)")
print(f"  notified_at : {notified_at}")

# Compare open_date as string to now
try:
    od = datetime.fromisoformat(str(open_date).replace("Z",""))
    is_open = od <= now
    print(f"\n  Wave open?  : {is_open}  (open_date={od}  vs  now={now})")
    if not is_open:
        delta = od - now
        print(f"  ⚠️  Wave opens in {delta}. Frontend may show it as open due to timezone difference.")
except Exception as e:
    print(f"  Could not parse open_date: {e}")

# ── existing draft requests ───────────────────────────────────────────────────
reqs = DB.execute(text("""
    SELECT request_type, COUNT(*) as cnt
    FROM draft_week_requests
    WHERE faculty_id = :fid AND config_id = :cfg_id
    GROUP BY request_type
"""), {"fid": fid, "cfg_id": cfg_id}).fetchall()

print(f"\nExisting draft requests:")
if reqs:
    for r in reqs:
        print(f"  {r[0]}: {r[1]}")
else:
    print("  (none)")

# ── existing traditional requests ────────────────────────────────────────────
old_reqs = DB.execute(text(
    "SELECT status, COUNT(*) FROM unavailability_requests WHERE faculty_id=:fid GROUP BY status"
), {"fid": fid}).fetchall()

print(f"\nExisting traditional (UnavailabilityRequest) records:")
if old_reqs:
    for r in old_reqs:
        print(f"  {r[0]}: {r[1]}")
    print("  ℹ️  These may cause the frontend to use the traditional submit path.")
else:
    print("  (none)")

print("\n✅  Diagnosis complete.")
