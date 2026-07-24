#!/usr/bin/env python3
"""
Database Diagnostic Script
Run this to inspect the draft_wave_configs table and identify data issues
"""

import sqlite3
import json
from datetime import datetime

def diagnose_database(db_path="facultyhub.db"):
    """Inspect the draft_wave_configs table"""

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Access columns by name
    cursor = conn.cursor()

    print("=" * 60)
    print("DATABASE DIAGNOSTIC REPORT")
    print("=" * 60)
    print()

    # Check if table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='draft_wave_configs'
    """)

    if not cursor.fetchone():
        print("❌ Table 'draft_wave_configs' does NOT exist")
        return

    print("✅ Table 'draft_wave_configs' exists")
    print()

    # Get table schema
    print("TABLE SCHEMA:")
    print("-" * 60)
    cursor.execute("PRAGMA table_info(draft_wave_configs)")
    columns = cursor.fetchall()

    for col in columns:
        print(f"  {col['name']:20s} {col['type']:15s} nullable={col['notnull']==0}")
    print()

    # Get all records
    cursor.execute("SELECT * FROM draft_wave_configs ORDER BY year DESC")
    rows = cursor.fetchall()

    print(f"RECORDS FOUND: {len(rows)}")
    print("-" * 60)

    if len(rows) == 0:
        print("❌ No configs found in database")
        return

    for i, row in enumerate(rows, 1):
        print(f"\n📋 Config #{i}:")
        print(f"  ID: {row['id']}")
        print(f"  Year: {row['year']}")
        print(f"  Status: {row['status']}")
        print()

        # Check each datetime field
        datetime_fields = ['close_date', 'created_at', 'activated_at', 'closed_at']

        for field in datetime_fields:
            value = row[field]
            print(f"  {field}:")
            print(f"    Raw value: {repr(value)}")
            print(f"    Type: {type(value).__name__}")

            if value is None:
                print(f"    Status: ✅ NULL (valid for optional fields)")
            elif isinstance(value, str):
                # Try to parse as datetime
                try:
                    # SQLite stores as 'YYYY-MM-DD HH:MM:SS' or ISO format
                    dt = datetime.fromisoformat(value.replace(' ', 'T'))
                    print(f"    Parsed: ✅ {dt}")
                except ValueError as e:
                    print(f"    Parsed: ❌ INVALID - {e}")
                    print(f"    ⚠️  THIS IS THE PROBLEM!")
            elif isinstance(value, (int, float)):
                # Unix timestamp
                try:
                    dt = datetime.fromtimestamp(value)
                    print(f"    Parsed: ✅ {dt}")
                except (ValueError, OSError) as e:
                    print(f"    Parsed: ❌ INVALID - {e}")
                    print(f"    ⚠️  THIS IS THE PROBLEM!")
            else:
                print(f"    Parsed: ❌ Unexpected type")
                print(f"    ⚠️  THIS IS THE PROBLEM!")

        print()

    print("=" * 60)
    print("DIAGNOSIS COMPLETE")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. If you see '⚠️  THIS IS THE PROBLEM!' above, that field is corrupted")
    print("2. Delete the config using the DELETE endpoint:")
    print(f"   DELETE /api/draft-waves/admin/configs/{{config_id}}")
    print("3. Create a fresh config via the admin UI")
    print()

    conn.close()


if __name__ == "__main__":
    import sys

    db_path = sys.argv[1] if len(sys.argv) > 1 else "facultyhub.db"

    print(f"Diagnosing database: {db_path}")
    print()

    try:
        diagnose_database(db_path)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
