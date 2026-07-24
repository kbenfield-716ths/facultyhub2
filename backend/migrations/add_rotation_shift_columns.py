"""
Add staffing-bound columns to schedule_periods and role to period_assignments.

  schedule_periods:   min_slots (default 1), max_slots (default 3)
  period_assignments: role (default 'provider')

Idempotent — safe to run more than once.

Usage:  python3 backend/migrations/add_rotation_shift_columns.py [path/to/staff.db]
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
        added = []

        period_cols = column_names(conn, "schedule_periods")
        if "min_slots" not in period_cols:
            conn.execute("ALTER TABLE schedule_periods ADD COLUMN min_slots INTEGER NOT NULL DEFAULT 1")
            added.append("schedule_periods.min_slots")
        if "max_slots" not in period_cols:
            conn.execute("ALTER TABLE schedule_periods ADD COLUMN max_slots INTEGER NOT NULL DEFAULT 3")
            added.append("schedule_periods.max_slots")

        assign_cols = column_names(conn, "period_assignments")
        if "role" not in assign_cols:
            conn.execute("ALTER TABLE period_assignments ADD COLUMN role VARCHAR NOT NULL DEFAULT 'provider'")
            added.append("period_assignments.role")

        conn.commit()
        if added:
            print(f"Added columns to {DB_PATH}: {', '.join(added)}")
        else:
            print(f"No changes needed — {DB_PATH} already migrated.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
