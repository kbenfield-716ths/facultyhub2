#!/usr/bin/env python3
"""
block_katie_waybill.py
----------------------
Creates FacultyBlock records for Katie Waybill (KMW7Z) covering
mid-October through mid-February in the 2026-2027 academic year.

These blocks are HARD STOPS — the scheduler will never place Katie
in any service slot during these weeks.

Usage (on Fly.io):
    fly ssh console -a facultyhub
    cd /app
    python3 block_katie_waybill.py               # preview (dry-run)
    python3 block_katie_waybill.py --apply        # create blocks in DB
    python3 block_katie_waybill.py --apply --clear  # clear existing first, then create
"""

import sys
import argparse
from datetime import date
from sqlalchemy import create_engine, text

# ── Config ────────────────────────────────────────────────────────────────────

FACULTY_ID  = "KMW7Z"
FACULTY_NAME = "Katie Waybill"
YEAR        = 2026          # academic year (2026 = AY 2026-2027)
REASON      = "Sleep schedule block (mid-Oct to mid-Feb)"

# Date range: Oct 15, 2026  →  Feb 15, 2027
BLOCK_START = date(2026, 10, 15)
BLOCK_END   = date(2027, 2, 15)

# ── DB ────────────────────────────────────────────────────────────────────────

def get_engine():
    import os
    candidates = [
        "/data/moonlighter.db",   # Fly.io volume (production)
        "./moonlighter.db",
        "./moonlighter_production.db",
        "./faculty_hub.db",
    ]
    for path in candidates:
        if os.path.exists(path):
            print(f"  Using database: {path}")
            return create_engine(f"sqlite:///{path}")
    raise RuntimeError(
        "No database found. Run this script on Fly.io:\n"
        "  fly ssh console -a facultyhub\n"
        "  cd /app && python3 block_katie_waybill.py --apply"
    )

# ── Main ──────────────────────────────────────────────────────────────────────

def run(apply: bool, clear_existing: bool):
    engine = get_engine()

    with engine.connect() as conn:
        # Check required tables
        tables = {r[0] for r in conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ))}
        for t in ("faculty_blocks", "service_weeks", "faculty"):
            if t not in tables:
                print(f"  ✗  Table '{t}' not found. Are you on the right database?")
                sys.exit(1)

        # Verify faculty exists
        row = conn.execute(text(
            "SELECT id, name FROM faculty WHERE id = :fid"
        ), {"fid": FACULTY_ID}).fetchone()
        if not row:
            print(f"  ✗  Faculty '{FACULTY_ID}' not found in database.")
            sys.exit(1)
        print(f"  ✓  Faculty found: {row[1]} ({row[0]})")

        # Find weeks that fall within the block range
        weeks = conn.execute(text("""
            SELECT id, week_number, label, start_date, end_date
            FROM service_weeks
            WHERE year = :year
            ORDER BY week_number
        """), {"year": YEAR}).fetchall()

        if not weeks:
            print(f"  ✗  No service weeks found for year {YEAR}.")
            sys.exit(1)

        target_weeks = []
        for w in weeks:
            # start_date stored as ISO string "YYYY-MM-DD"
            try:
                start = date.fromisoformat(str(w[3])[:10])
                end   = date.fromisoformat(str(w[4])[:10])
            except Exception:
                continue

            # Include week if it overlaps with [BLOCK_START, BLOCK_END]
            if start <= BLOCK_END and end >= BLOCK_START:
                target_weeks.append(w)

        print(f"\n  Weeks in range {BLOCK_START} → {BLOCK_END}:")
        for w in target_weeks:
            print(f"    Week {w[1]:2d}  {w[3]} → {w[4]}  ({w[2]})")

        print(f"\n  Total weeks to block: {len(target_weeks)}")

        if not apply:
            print("\n  DRY RUN — no changes made.")
            print("  Run with --apply to create the blocks.")
            return

        # Optional: clear existing blocks for this faculty in this year
        if clear_existing:
            week_ids = [w[0] for w in weeks]
            placeholders = ",".join(f"'{wid}'" for wid in week_ids)
            deleted = conn.execute(text(f"""
                DELETE FROM faculty_blocks
                WHERE faculty_id = :fid
                  AND week_id IN ({placeholders})
            """), {"fid": FACULTY_ID})
            conn.commit()
            print(f"\n  Cleared {deleted.rowcount} existing block(s) for {FACULTY_NAME} in AY{YEAR}-{YEAR+1}.")

        # Create blocks
        import uuid
        from datetime import datetime

        created = 0
        skipped = 0
        for w in target_weeks:
            week_id = w[0]
            # Check if block already exists
            existing = conn.execute(text("""
                SELECT id FROM faculty_blocks
                WHERE faculty_id = :fid AND week_id = :wid
            """), {"fid": FACULTY_ID, "wid": week_id}).fetchone()

            if existing:
                skipped += 1
                continue

            conn.execute(text("""
                INSERT INTO faculty_blocks (id, faculty_id, week_id, reason, created_at)
                VALUES (:id, :fid, :wid, :reason, :now)
            """), {
                "id":     str(uuid.uuid4()),
                "fid":    FACULTY_ID,
                "wid":    week_id,
                "reason": REASON,
                "now":    datetime.utcnow().isoformat(),
            })
            created += 1

        conn.commit()
        print(f"\n  ✓  Created {created} new block(s)  (skipped {skipped} already existing)")
        print(f"\n  Done. {FACULTY_NAME} is now blocked from scheduling for")
        print(f"  weeks {target_weeks[0][1]}–{target_weeks[-1][1]} ({BLOCK_START} → {BLOCK_END}).")
        print(f"\n  Next step: re-run the schedule generator or use")
        print(f"  '🧹 Remove Block Violations' in the admin UI to clean up")
        print(f"  any existing assignments that now conflict with these blocks.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Block Katie Waybill from scheduling mid-Oct to mid-Feb"
    )
    parser.add_argument("--apply",  action="store_true",
        help="Actually create the blocks (default is dry-run)")
    parser.add_argument("--clear",  action="store_true",
        help="Clear existing blocks for this faculty/year before creating new ones")
    args = parser.parse_args()

    print(f"\n{'='*55}")
    print(f"  Katie Waybill Block Script")
    print(f"  Faculty: {FACULTY_ID}  |  Year: AY{YEAR}-{YEAR+1}")
    print(f"  Range: {BLOCK_START} → {BLOCK_END}")
    print(f"  Mode: {'APPLY' if args.apply else 'DRY RUN'}")
    print(f"{'='*55}\n")

    run(apply=args.apply, clear_existing=args.clear)
