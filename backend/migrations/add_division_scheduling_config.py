"""
Add per-division self-scheduling policy: divisions.scheduling_config (JSON).

Holds how end users get onto the schedule (method) and at what cadence:
  {"method": "manual|fcfs|priority|wave",
   "cadence": "annual|quarterly|monthly",
   "self_scheduling_open": false, "notes": ""}

Idempotent — safe to run more than once.

Usage:  python3 backend/migrations/add_division_scheduling_config.py [path/to/staff.db]
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parents[2] / "staff.db")


def column_names(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def main():
    conn = sqlite3.connect(DB_PATH)
    try:
        cols = column_names(conn, "divisions")
        if "scheduling_config" not in cols:
            conn.execute("ALTER TABLE divisions ADD COLUMN scheduling_config TEXT NOT NULL DEFAULT '{}'")
            conn.commit()
            print(f"Added divisions.scheduling_config to {DB_PATH}")
        else:
            print(f"No changes needed — {DB_PATH} already migrated.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
