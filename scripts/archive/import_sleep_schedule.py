#!/usr/bin/env python3
"""
import_sleep_schedule.py
------------------------
Imports a sleep-schedule CSV as FacultyBlock records in FacultyHub.

CSV format expected:
    Start Day,FACULTY_ID1,FACULTY_ID2,...
    MM/DD/YY,0,1,0,...

A value of 1 means that faculty member is on sleep schedule that week
and should be blocked from service assignments.

Usage (run from FacultyHub directory on Fly.io):
    python3 import_sleep_schedule.py sleep.csv
    python3 import_sleep_schedule.py sleep.csv --dry-run
    python3 import_sleep_schedule.py sleep.csv --clear-existing

On Fly.io:
    fly ssh console -a facultyhub
    cd /app
    python3 import_sleep_schedule.py sleep.csv --dry-run
"""

import sys
import csv
import uuid
import argparse
import os
from datetime import datetime, date

SLEEP_REASON = "Sleep schedule"


# ---------------------------------------------------------------------------
# Database connection (SQLAlchemy raw SQL — no ORM models needed)
# ---------------------------------------------------------------------------

def get_engine():
    """
    Return a SQLAlchemy engine pointed at the correct database.
    Uses DATABASE_URL env var on Fly.io (PostgreSQL), otherwise finds a
    local SQLite file for development use.
    """
    from sqlalchemy import create_engine

    # Try paths in priority order — mirrors what backend/models.py does
    candidates = [
        "/data/moonlighter.db",          # Fly.io volume mount (production)
        "./moonlighter.db",               # Fly.io fallback / local
        "moonlighter_production.db",      # local backup
        "faculty_hub.db",                 # local backup
    ]

    # Also honour an explicit DATABASE_URL if set (PostgreSQL, etc.)
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url:
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        print(f"  Using DATABASE_URL from environment")
        return create_engine(db_url)

    for path in candidates:
        if os.path.exists(path):
            print(f"  Using SQLite database: {path}")
            return create_engine(f"sqlite:///{path}")

    raise RuntimeError(
        "No database found. Looked for: " + ", ".join(candidates)
    )


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------

def parse_csv(csv_path: str):
    faculty_ids = []
    rows = []

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        if not headers or len(headers) < 2:
            raise ValueError("CSV must have at least two columns: Start Day + one faculty ID")

        faculty_ids = [h.strip() for h in headers[1:]]

        for raw_row in reader:
            start_raw = raw_row.get(headers[0], "").strip()
            if not start_raw:
                continue
            try:
                start = datetime.strptime(start_raw, "%m/%d/%y").date()
            except ValueError:
                print(f"  ⚠  Skipping unparseable date: {start_raw!r}")
                continue

            blocked = {fid: (raw_row.get(fid, "0").strip() == "1") for fid in faculty_ids}
            rows.append({"start_date": start.isoformat(), "blocked": blocked})

    return faculty_ids, rows


# ---------------------------------------------------------------------------
# Import logic
# ---------------------------------------------------------------------------

def run_import(csv_path: str, dry_run: bool = False, clear_existing: bool = False):
    from sqlalchemy import text

    print("\n=== Sleep Schedule Import ===\n")

    engine = get_engine()
    faculty_ids, rows = parse_csv(csv_path)
    print(f"CSV faculty columns : {faculty_ids}")
    print(f"CSV data rows       : {len(rows)}")

    with engine.connect() as conn:

        # ── Verify required tables exist (guard against partial local backups) ─
        for table in ("faculty", "service_weeks", "faculty_blocks"):
            try:
                conn.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))
            except Exception:
                print(
                    f"\n❌  Table '{table}' not found in this database.\n"
                    f"   The local SQLite backup is incomplete.\n"
                    f"   Run this script on Fly.io where the full PostgreSQL database is available:\n\n"
                    f"     fly ssh console -a <your-app-name>\n"
                    f"     cd /app\n"
                    f"     python3 import_sleep_schedule.py sleep.csv --dry-run\n"
                )
                return

        # ── Validate faculty IDs ─────────────────────────────────────────────
        faculty_map = {}
        unknown_ids = []
        for fid in faculty_ids:
            result = conn.execute(
                text("SELECT id, name FROM faculty WHERE id = :id"), {"id": fid}
            ).fetchone()
            if result:
                faculty_map[fid] = result[1]
            else:
                unknown_ids.append(fid)

        if unknown_ids:
            print(f"\n⚠  WARNING: The following faculty IDs were NOT found in the database:")
            for uid in unknown_ids:
                print(f"   - {uid!r}")
            print("   These columns will be skipped.\n")

        if not faculty_map:
            print("❌  No valid faculty IDs found. Aborting.")
            return

        print(f"\nValid faculty to process:")
        for fid, name in faculty_map.items():
            print(f"   {fid} → {name}")

        # ── Optionally clear existing sleep blocks ───────────────────────────
        cleared = 0
        if clear_existing and not dry_run:
            for fid in faculty_map:
                r = conn.execute(
                    text("DELETE FROM faculty_blocks WHERE faculty_id = :fid AND reason = :reason"),
                    {"fid": fid, "reason": SLEEP_REASON}
                )
                cleared += r.rowcount
            conn.commit()
            print(f"\n🗑  Cleared {cleared} existing sleep blocks.\n")

        # ── Map start_date → service_week id/label ───────────────────────────
        all_dates = list({r["start_date"] for r in rows})
        sw_by_date = {}
        for ds in all_dates:
            result = conn.execute(
                text("SELECT id, label FROM service_weeks WHERE start_date = :ds"), {"ds": ds}
            ).fetchone()
            if result:
                sw_by_date[ds] = (result[0], result[1])

        # ── Process rows ─────────────────────────────────────────────────────
        created = 0
        skipped_no_week = []
        skipped_duplicate = 0

        print(f"\n--- Processing {len(rows)} CSV rows ---")

        for row in rows:
            ds = row["start_date"]
            sw = sw_by_date.get(ds)

            if sw is None:
                skipped_no_week.append(ds)
                print(f"  ⚠  No service week for {ds} — skipping")
                continue

            sw_id, sw_label = sw

            for fid, is_blocked in row["blocked"].items():
                if fid not in faculty_map or not is_blocked:
                    continue

                existing = conn.execute(
                    text("SELECT id FROM faculty_blocks WHERE faculty_id = :fid AND week_id = :wid"),
                    {"fid": fid, "wid": sw_id}
                ).fetchone()

                if existing:
                    skipped_duplicate += 1
                    continue

                faculty_name = faculty_map[fid]
                print(f"  {'[DRY RUN] ' if dry_run else ''}✅  Block: {faculty_name} — {sw_label} ({ds})")

                if not dry_run:
                    conn.execute(
                        text("""INSERT INTO faculty_blocks (id, faculty_id, week_id, reason, created_at)
                                VALUES (:id, :fid, :wid, :reason, :ts)"""),
                        {
                            "id": str(uuid.uuid4()),
                            "fid": fid,
                            "wid": sw_id,
                            "reason": SLEEP_REASON,
                            "ts": datetime.utcnow().isoformat()
                        }
                    )
                    created += 1

        if not dry_run:
            conn.commit()

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n=== Summary ===")
    if dry_run:
        print(f"  DRY RUN — no changes were written to the database")
    print(f"  Blocks created      : {created if not dry_run else '(dry run — see above)'}")
    print(f"  Skipped (no week)   : {len(skipped_no_week)}")
    if skipped_no_week:
        print(f"    Dates: {skipped_no_week}")
    print(f"  Skipped (duplicate) : {skipped_duplicate}")
    if unknown_ids:
        print(f"  Unknown faculty IDs : {unknown_ids}")
    print()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import a sleep-schedule CSV as FacultyBlock records."
    )
    parser.add_argument("csv_file", help="Path to the sleep schedule CSV")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be imported without writing to the database",
    )
    parser.add_argument(
        "--clear-existing",
        action="store_true",
        help="Delete all existing 'Sleep schedule' blocks before importing",
    )
    args = parser.parse_args()
    run_import(args.csv_file, dry_run=args.dry_run, clear_existing=args.clear_existing)
