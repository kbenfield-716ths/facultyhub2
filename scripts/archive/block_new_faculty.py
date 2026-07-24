#!/usr/bin/env python3
"""
block_new_faculty.py
--------------------
Creates FacultyBlock records for new faculty who join mid-year and cannot
cover inpatient service weeks during their onboarding period.

Blocks: July 1, 2026 → September 14, 2026  (weeks ~2–11)

Faculty blocked:
  - Lauren Ivey     (IVEY)
  - Samual Konkol   (SK8JQ)
  - Kierra Cerda    (XXB8YS)

Usage (on Fly.io):
    fly ssh console -a facultyhub
    cd /app
    python3 block_new_faculty.py               # preview (dry-run)
    python3 block_new_faculty.py --apply        # create blocks in DB
    python3 block_new_faculty.py --apply --clear  # clear existing first, then create
"""

import sys
import argparse
from datetime import date, datetime
import sqlite3

# ── Config ────────────────────────────────────────────────────────────────────

YEAR        = 2026
BLOCK_START = date(2026, 7, 1)
BLOCK_END   = date(2026, 9, 14)   # mid-September
REASON      = "New faculty onboarding block (Jul – mid-Sep 2026)"

NEW_FACULTY = [
    ("IVEY",   "Lauren Ivey"),
    ("SK8JQ",  "Samual Konkol"),
    ("XXB8YS", "Kierra Cerda"),
]

# ── DB ────────────────────────────────────────────────────────────────────────

def get_conn():
    import os
    candidates = [
        "/data/moonlighter.db",
        os.path.join(os.path.dirname(__file__), "moonlighter.db"),
        "./moonlighter.db",
    ]
    for path in candidates:
        if os.path.exists(path):
            print(f"[DB] Using database at {path}")
            conn = sqlite3.connect(path, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=10000")
            return conn
    raise FileNotFoundError(
        "Cannot find moonlighter.db. "
        "Run this script on Fly.io: fly ssh console -a facultyhub"
    )

# ── Core logic ────────────────────────────────────────────────────────────────

def run(apply: bool, clear_existing: bool):
    import uuid

    conn = get_conn()

    # Verify tables exist
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    for required in ("faculty", "service_weeks", "faculty_blocks"):
        if required not in tables:
            print(f"  ✗  Table '{required}' not found. Wrong database?")
            sys.exit(1)

    # Load all weeks for this academic year
    all_weeks = conn.execute(
        "SELECT id, week_number, week_type, start_date, end_date "
        "FROM service_weeks WHERE year = ? ORDER BY week_number",
        (YEAR,)
    ).fetchall()

    if not all_weeks:
        print(f"  ✗  No service weeks found for year {YEAR}.")
        sys.exit(1)

    # Find weeks that overlap with the block range
    target_weeks = []
    for w in all_weeks:
        start = date.fromisoformat(str(w["start_date"])[:10])
        end   = date.fromisoformat(str(w["end_date"])[:10])
        if start <= BLOCK_END and end >= BLOCK_START:
            target_weeks.append(w)

    print(f"\n  Weeks in block range  {BLOCK_START}  →  {BLOCK_END}:")
    for w in target_weeks:
        print(f"    Week {w['week_number']:2d}  {w['start_date']} → {w['end_date']}  ({w['week_type']})")
    print(f"\n  Total weeks to block: {len(target_weeks)}")

    grand_total_created = 0
    grand_total_skipped = 0

    for faculty_id, faculty_name in NEW_FACULTY:
        print(f"\n{'─'*55}")
        print(f"  Faculty: {faculty_name}  ({faculty_id})")

        row = conn.execute(
            "SELECT id, name FROM faculty WHERE id = ?", (faculty_id,)
        ).fetchone()
        if not row:
            print(f"  ✗  Not found in database — skipping.")
            continue
        print(f"  ✓  Found in database")

        if clear_existing and apply:
            cur = conn.execute(
                "DELETE FROM faculty_blocks WHERE faculty_id = ? "
                "AND week_id IN (SELECT id FROM service_weeks WHERE year = ?) "
                "AND reason = ?",
                (faculty_id, YEAR, REASON)
            )
            conn.commit()
            if cur.rowcount:
                print(f"  Cleared {cur.rowcount} existing onboarding block(s).")

        created = 0
        skipped = 0

        for w in target_weeks:
            week_id = w["id"]

            existing = conn.execute(
                "SELECT id FROM faculty_blocks WHERE faculty_id = ? AND week_id = ?",
                (faculty_id, week_id)
            ).fetchone()

            if existing:
                skipped += 1
                continue

            if apply:
                conn.execute(
                    "INSERT INTO faculty_blocks (id, faculty_id, week_id, reason, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), faculty_id, week_id, REASON,
                     datetime.utcnow().isoformat(), datetime.utcnow().isoformat())
                )
                created += 1
            else:
                created += 1   # dry-run count

        if apply:
            conn.commit()
            print(f"  ✓  Created {created} block(s)  |  Skipped {skipped} (already existed)")
        else:
            print(f"  [DRY RUN] Would create {created} block(s)  |  Skip {skipped} (already exist)")

        grand_total_created += created
        grand_total_skipped += skipped

    conn.close()
    print(f"\n{'='*55}")
    if apply:
        print(f"  ✅  Done. Created {grand_total_created} total blocks across {len(NEW_FACULTY)} faculty.")
        print(f"\n  Next steps:")
        print(f"    1. Click '🧹 Remove Block Violations' in admin UI to clear")
        print(f"       any existing assignments that conflict with these blocks.")
        print(f"    2. Re-run '⚡ Generate Assignments' to fill those slots.")
    else:
        print(f"  [DRY RUN]  Would create {grand_total_created} block(s).")
        print(f"  Re-run with --apply to commit.")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Block new faculty during onboarding period")
    parser.add_argument("--apply",  action="store_true", help="Write blocks to DB (default: dry-run)")
    parser.add_argument("--clear",  action="store_true", help="Clear existing onboarding blocks first")
    args = parser.parse_args()

    print("=" * 55)
    print("  New Faculty Onboarding Blocks")
    print(f"  Faculty: {', '.join(n for _, n in NEW_FACULTY)}")
    print(f"  Range:   {BLOCK_START}  →  {BLOCK_END}")
    print(f"  Mode:    {'APPLY' if args.apply else 'DRY RUN'}")
    print("=" * 55)

    run(apply=args.apply, clear_existing=args.clear)


if __name__ == "__main__":
    main()
