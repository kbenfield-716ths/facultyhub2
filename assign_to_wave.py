#!/usr/bin/env python3
"""
assign_to_wave.py — Add a faculty member to a wave.

Usage:
    python3 assign_to_wave.py              # list waves only
    python3 assign_to_wave.py SK8JQ        # show waves + this faculty's status
    python3 assign_to_wave.py SK8JQ 2      # assign SK8JQ to wave #2 (from list)
"""

import os, sys, uuid
from datetime import datetime

DB_PATHS = ["/data/moonlighter.db", "./moonlighter.db", "/app/moonlighter.db"]
db_path = next((p for p in DB_PATHS if os.path.exists(p)), None)
if not db_path:
    print("ERROR: Could not find database."); sys.exit(1)

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
db = sessionmaker(bind=engine)()

faculty_arg = sys.argv[1] if len(sys.argv) > 1 else None
wave_arg    = sys.argv[2] if len(sys.argv) > 2 else None

# ── active config ─────────────────────────────────────────────────────────────
config = db.execute(text(
    "SELECT id, year FROM draft_wave_configs WHERE status='active'"
)).fetchone()
if not config:
    print("ERROR: No active draft config."); sys.exit(1)
cfg_id, cfg_year = config

# ── list waves ────────────────────────────────────────────────────────────────
waves = db.execute(text(
    "SELECT id, name, open_date FROM draft_waves WHERE config_id=:c ORDER BY wave_order"
), {"c": cfg_id}).fetchall()

now = datetime.utcnow()
print(f"\nWaves for {cfg_year} config:")
for i, (wid, wname, wopen) in enumerate(waves):
    try:
        od = datetime.fromisoformat(str(wopen).replace("Z",""))
        status = "OPEN" if od <= now else f"opens {wopen}"
    except:
        status = str(wopen)
    print(f"  [{i+1}] {wname}  ({status})")

if not faculty_arg:
    print("\nRun with faculty ID to assign:  python3 assign_to_wave.py SK8JQ 2")
    sys.exit(0)

# ── find faculty ──────────────────────────────────────────────────────────────
row = db.execute(text(
    "SELECT id, name FROM faculty WHERE email=:v OR id=:v2"
), {"v": faculty_arg, "v2": faculty_arg.upper()}).fetchone()
if not row:
    print(f"\nERROR: No faculty found for {faculty_arg!r}"); sys.exit(1)
fid, fname = row
print(f"\nFaculty: {fname} ({fid})")

# ── check existing assignment ─────────────────────────────────────────────────
existing = db.execute(text("""
    SELECT dw.name FROM wave_faculty_assignments wfa
    JOIN draft_waves dw ON dw.id = wfa.wave_id
    WHERE wfa.faculty_id=:fid AND dw.config_id=:cfg_id
"""), {"fid": fid, "cfg_id": cfg_id}).fetchone()
if existing:
    print(f"Already assigned to wave: {existing[0]}"); sys.exit(0)

if not wave_arg:
    print("Run again with wave number to assign:  python3 assign_to_wave.py SK8JQ 2")
    sys.exit(0)

# ── assign ────────────────────────────────────────────────────────────────────
try:
    idx = int(wave_arg) - 1
    assert 0 <= idx < len(waves)
except:
    print(f"ERROR: Invalid wave number {wave_arg!r}"); sys.exit(1)

wave_id, wave_name, _ = waves[idx]

db.execute(text("""
    INSERT INTO wave_faculty_assignments (id, wave_id, faculty_id, created_at)
    VALUES (:id, :wave_id, :faculty_id, :now)
"""), {"id": str(uuid.uuid4()), "wave_id": wave_id, "faculty_id": fid,
       "now": datetime.utcnow().isoformat()})
db.commit()

print(f"✅  {fname} assigned to '{wave_name}'. They can now submit requests.")
