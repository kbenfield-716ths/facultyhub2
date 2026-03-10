#!/usr/bin/env python3
"""
import_allocations.py
---------------------
Imports faculty service-week allocations from a CSV file (Book2 format)
and writes them to the faculty table in the database.

Expected CSV columns:
    (name), MICU, APP, procedures, consults, Backup

The first column is the faculty last name (used for matching).
Blank cells mean "no change" — the existing value is kept.
Zero means "zero weeks allocated for this service".
"Hospitalists" row is skipped (not a real faculty member).

Usage (on Fly.io):
    fly ssh console -a facultyhub
    cd /app
    python3 import_allocations.py                        # dry-run preview
    python3 import_allocations.py --apply                # write to DB
    python3 import_allocations.py --apply --csv /path    # custom CSV path
"""

import sys
import argparse
import csv
import io
import sqlite3
import os

# ── DB ────────────────────────────────────────────────────────────────────────

def get_conn():
    """Return a sqlite3 connection with a short busy timeout so it fails fast
    instead of hanging when the app is holding a lock."""
    candidates = [
        "/data/moonlighter.db",
        os.path.join(os.path.dirname(__file__), "moonlighter.db"),
        "moonlighter.db",
    ]
    for path in candidates:
        if os.path.exists(path):
            print(f"[DB] Using database at {path}")
            conn = sqlite3.connect(path, timeout=10)
            conn.row_factory = sqlite3.Row
            # Use WAL so reads don't block behind the running app's writes
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=10000")  # 10 s then error, not hang
            return conn
    raise FileNotFoundError(
        "Cannot find moonlighter.db. "
        "Run this script on Fly.io: fly ssh console -a facultyhub"
    )

# ── Allocation CSV ─────────────────────────────────────────────────────────────

# Embedded Book2 data — paste your latest CSV here as a fallback,
# or pass --csv to load from a file.
EMBEDDED_CSV = """,MICU,APP,procedures,consults,Backup
Albon,,,,7,3
Barros,5,,3,3,2
Bell,4,0,0,0,2
Bonham,6,2,4,3,2
Burks,,,6,,
Cerda,5,2,,,2
Egressy,8,1,,,0
Enfield,2,8,,,3
Harris,,,,,3
Ivey,4,2,,6,2
Kadl,4,4,4,0,2
Kim,,4,,5,2
Konkol,5,2,2,,2
MacLeod,6,3,4,0,2
Mandrell,9,8,8,0,2
Malik,6,,,5,2
Mihalek,9,6,,,2
Noth,,2,,,3
Patel,9,,4,,2
Paul,,,,12,2
Schecter,7,1,4,,2
Scialla,,,,9,2
Somerville,5,3,3,,2
Sturek,4,2,2,,2
Waybill,4,2,,2,2
Hospitalists,,,8,,0
"""

def parse_csv(source: str) -> list:
    """Return list of dicts from CSV source string."""
    rows = []
    reader = csv.DictReader(io.StringIO(source.lstrip("\ufeff")))
    for row in reader:
        last_name = row.get("", "").strip()
        if not last_name or last_name.lower() == "hospitalists":
            continue  # skip blank rows and the Hospitalists placeholder
        rows.append({
            "last_name": last_name,
            "micu":       _int_or_none(row.get("MICU", "")),
            "app_icu":    _int_or_none(row.get("APP", "")),
            "procedures": _int_or_none(row.get("procedures", "")),
            "consults":   _int_or_none(row.get("consults", "")),
            "backup":     _int_or_none(row.get("Backup", "")),
        })
    return rows

def _int_or_none(val: str):
    v = val.strip()
    if v == "":
        return None   # blank = "don't touch"
    try:
        return int(float(v))
    except ValueError:
        return None

# ── Matching ──────────────────────────────────────────────────────────────────

def load_faculty(conn) -> dict:
    """Return dict: last_name_lower -> (id, full_name)"""
    rows = conn.execute("SELECT id, name FROM faculty WHERE active = 1").fetchall()
    result = {}
    for row in rows:
        last = row["name"].split()[-1].lower()
        result[last] = (row["id"], row["name"])
    return result

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Import faculty allocation targets into the DB")
    parser.add_argument("--apply", action="store_true", help="Actually write changes (default: dry-run)")
    parser.add_argument("--csv", metavar="PATH", help="Path to CSV file (default: embedded Book2 data)")
    args = parser.parse_args()

    # Load CSV
    if args.csv:
        with open(args.csv, encoding="utf-8-sig") as f:
            source = f.read()
        print(f"[CSV] Loaded from {args.csv}")
    else:
        source = EMBEDDED_CSV
        print("[CSV] Using embedded Book2 data")

    rows = parse_csv(source)
    print(f"[CSV] Parsed {len(rows)} faculty rows\n")

    conn = get_conn()
    faculty_map = load_faculty(conn)

    col_labels = {
        "micu":       ("micu_weeks",        "MICU"),
        "app_icu":    ("app_icu_weeks",     "APP-ICU"),
        "procedures": ("procedure_weeks",   "Procedures"),
        "consults":   ("consult_weeks",     "Consults"),
        "backup":     ("backup_weeks",      "Backup"),
    }

    updates = []   # list of (faculty_id, full_name, db_col, label, old_val, new_val)
    unmatched = []

    for row in rows:
        key = row["last_name"].lower()
        if key not in faculty_map:
            unmatched.append(row["last_name"])
            continue

        fid, fname = faculty_map[key]

        current = conn.execute(
            "SELECT micu_weeks, app_icu_weeks, procedure_weeks, consult_weeks, backup_weeks "
            "FROM faculty WHERE id = ?", (fid,)
        ).fetchone()

        current_vals = {
            "micu":       current["micu_weeks"],
            "app_icu":    current["app_icu_weeks"],
            "procedures": current["procedure_weeks"],
            "consults":   current["consult_weeks"],
            "backup":     current["backup_weeks"],
        }

        for key_name, (db_col, label) in col_labels.items():
            new_val = row[key_name]
            if new_val is None:
                continue   # blank in CSV — leave as-is
            old_val = current_vals[key_name]
            if new_val != old_val:
                updates.append((fid, fname, db_col, label, old_val, new_val))

    # Print preview
    print(f"{'Faculty':<22} {'Service':<12} {'Old':>6} {'New':>6}  {'Change':>8}")
    print("-" * 62)
    totals_new = {"MICU": 0, "APP-ICU": 0, "Procedures": 0, "Consults": 0, "Backup": 0}

    # Also compute new totals from the CSV data
    for row in rows:
        for key_name, (_, label) in col_labels.items():
            v = row[key_name]
            if v is not None:
                totals_new[label] = totals_new.get(label, 0) + v

    for fid, fname, db_col, label, old_val, new_val in updates:
        diff = (new_val or 0) - (old_val or 0)
        diff_str = f"+{diff}" if diff > 0 else str(diff)
        print(f"  {fname:<20} {label:<12} {old_val or 0:>6} {new_val:>6}  {diff_str:>8}")

    print(f"\n{len(updates)} field(s) to update across {len(set(u[0] for u in updates))} faculty.")

    if unmatched:
        print(f"\n⚠  Could not match last names: {', '.join(unmatched)}")

    print("\n=== ALLOCATION TOTALS (from CSV) ===")
    slots_needed = {"MICU": 104, "APP-ICU": 52, "Procedures": 52, "Consults": 52, "Backup": 52}
    for svc, total in totals_new.items():
        needed = slots_needed.get(svc, "?")
        status = "✓" if total >= needed else f"⚠  SHORT by {needed - total}"
        print(f"  {svc:<12} allocated={total:>4}  needed={needed:>4}  {status}")

    if not args.apply:
        print("\n[DRY RUN] No changes written. Re-run with --apply to commit.")
        conn.close()
        return

    # Apply updates
    for fid, fname, db_col, label, old_val, new_val in updates:
        conn.execute(
            f"UPDATE faculty SET {db_col} = ? WHERE id = ?",
            (new_val, fid)
        )
    conn.commit()
    conn.close()
    print(f"\n✅ Applied {len(updates)} updates to the database.")

if __name__ == "__main__":
    main()
