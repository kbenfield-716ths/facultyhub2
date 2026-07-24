#!/usr/bin/env python3
"""
Apply targeted changes from grid_changes_to_apply.csv to service_week_assignments.

Uses sqlite3 directly — no framework dependencies.

Usage:
    python3 apply_grid_changes.py           # dry run (preview only)
    python3 apply_grid_changes.py --apply   # commit to database

On Fly.io:
    fly ssh console -a facultyhub
    cd /app
    python3 apply_grid_changes.py           # preview first
    python3 apply_grid_changes.py --apply   # then commit
"""

import argparse
import csv
import os
import sqlite3
import sys
import uuid

# ── Paths ────────────────────────────────────────────────────────────────────
DB_PATH          = "/data/moonlighter.db"
CHANGES_FILE     = "grid_changes_to_apply.csv"
ACADEMIC_YEAR    = 2026

# ── Service types that map to service_week_assignments rows ──────────────────
SERVICE_TYPES = {'MICU', 'APP-ICU', 'Consults', 'Procedures', 'Backup'}


def load_changes(path):
    changes = []
    with open(path, newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            changes.append((
                int(row['Week #']),
                row['Faculty'].strip(),
                row['Old Value'].strip(),
                row['New Value'].strip(),
            ))
    return changes


def resolve_name(cursor, display_name):
    """Match a grid display name to a faculty ID using progressive fuzzy matching."""
    dn = display_name.lower().strip()
    cursor.execute("SELECT id, name FROM faculty WHERE active = 1")
    rows = cursor.fetchall()

    # 1. Exact match
    for fid, name in rows:
        if name.lower() == dn:
            return fid

    # 2. DB name contains full display name
    for fid, name in rows:
        if dn in name.lower():
            return fid

    # 3. All tokens of display name present in DB name
    tokens = dn.split()
    for fid, name in rows:
        if all(t in name.lower() for t in tokens):
            return fid

    # 4. Last name only (only if unique match)
    last = tokens[-1] if tokens else ''
    matches = [(fid, name) for fid, name in rows if last in name.lower()]
    if len(matches) == 1:
        return matches[0][0]

    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true',
                        help='Write changes to DB (default is dry run)')
    parser.add_argument('--changes', default=CHANGES_FILE)
    parser.add_argument('--year', type=int, default=ACADEMIC_YEAR)
    parser.add_argument('--db', default=DB_PATH)
    args = parser.parse_args()

    dry_run = not args.apply

    print("=" * 65)
    print("Faculty Grid — Targeted Change Applicator")
    print("=" * 65)
    print(f"  DB           : {args.db}")
    print(f"  Changes file : {args.changes}")
    print(f"  Year         : {args.year}")
    print(f"  Mode         : {'DRY RUN (preview only)' if dry_run else '⚡ APPLY — writing to DB'}")
    print()

    if not os.path.exists(args.db):
        print(f"❌ Database not found: {args.db}")
        sys.exit(1)

    if not os.path.exists(args.changes):
        print(f"❌ Changes file not found: {args.changes}")
        sys.exit(1)

    changes = load_changes(args.changes)
    print(f"  {len(changes)} changes loaded\n")
    print("─" * 65)

    conn = sqlite3.connect(args.db)
    cursor = conn.cursor()

    stats = {'created': 0, 'deleted': 0, 'swapped': 0, 'skipped': 0}
    unresolved = []

    for week, display_name, old_val, new_val in changes:
        week_id    = f"W{week:02d}-{args.year}"
        faculty_id = resolve_name(cursor, display_name)

        if faculty_id is None:
            print(f"  ⚠️  UNRESOLVED: '{display_name}' (week {week}) — skipped")
            unresolved.append(display_name)
            stats['skipped'] += 1
            continue

        removing = old_val in SERVICE_TYPES
        adding   = new_val in SERVICE_TYPES

        if removing and adding:
            action_label = f"SWAP  {old_val} → {new_val}"
        elif adding:
            action_label = f"CREATE {new_val}"
        else:
            action_label = f"DELETE {old_val}"

        print(f"  Week {week:2d} | {display_name:<22} ({faculty_id}) | {action_label}")

        if not dry_run:
            if removing:
                cursor.execute("""
                    DELETE FROM service_week_assignments
                    WHERE faculty_id = ? AND week_id = ? AND service_type = ?
                """, (faculty_id, week_id, old_val))
                if cursor.rowcount == 0:
                    print(f"           ⚠️  No existing {old_val} record found to delete")

            if adding:
                cursor.execute("""
                    SELECT id FROM service_week_assignments
                    WHERE faculty_id = ? AND week_id = ? AND service_type = ?
                """, (faculty_id, week_id, new_val))
                if cursor.fetchone() is None:
                    cursor.execute("""
                        INSERT INTO service_week_assignments
                            (id, faculty_id, week_id, service_type, imported, is_manual)
                        VALUES (?, ?, ?, ?, 1, 0)
                    """, (str(uuid.uuid4()), faculty_id, week_id, new_val))
                else:
                    print(f"           ℹ️  {new_val} already exists — skipped")

        if removing and adding:
            stats['swapped'] += 1
        elif adding:
            stats['created'] += 1
        else:
            stats['deleted'] += 1

    if not dry_run:
        conn.commit()
        print(f"\n✅ Committed to database.")
    else:
        print(f"\n  (Dry run — nothing written)")

    conn.close()

    print("─" * 65)
    print(f"\nSummary:")
    print(f"  Created  : {stats['created']}")
    print(f"  Deleted  : {stats['deleted']}")
    print(f"  Swapped  : {stats['swapped']}")
    print(f"  Skipped  : {stats['skipped']}")

    if unresolved:
        print(f"\n⚠️  Unresolved names (not found in faculty table):")
        for name in sorted(set(unresolved)):
            print(f"   - {name}")


if __name__ == '__main__':
    main()
