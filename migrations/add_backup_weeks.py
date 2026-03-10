"""
Migration: Add backup_weeks column to faculty table.

backup_weeks tracks how many Backup service weeks a faculty member
is allocated per academic year. Backup is a 5th service lane
(1 provider per week) scheduled alongside MICU, APP-ICU, Procedures, Consults.

Run once on Fly.io:
    fly ssh console -a <your-app-name>
    cd /app
    python3 migrations/add_backup_weeks.py
"""

import sqlite3
import sys
import os


def find_database():
    candidates = [
        "/data/moonlighter.db",
        "/app/moonlighter.db",
        "./moonlighter.db",
        "moonlighter.db",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def migrate():
    db_path = find_database()
    if not db_path:
        print("❌  Could not find database. Set path manually or run from /app.")
        sys.exit(1)

    print(f"✅  Found database: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(faculty)")
        columns = [row[1] for row in cursor.fetchall()]

        if "backup_weeks" in columns:
            print("✅  Column 'backup_weeks' already exists — skipping.")
            conn.close()
            return 0

        print("📝  Adding 'backup_weeks' column to faculty table...")
        cursor.execute(
            "ALTER TABLE faculty ADD COLUMN backup_weeks INTEGER NOT NULL DEFAULT 0"
        )
        conn.commit()

        # Verify
        cursor.execute("PRAGMA table_info(faculty)")
        columns = [row[1] for row in cursor.fetchall()]
        if "backup_weeks" in columns:
            cursor.execute("SELECT COUNT(*) FROM faculty")
            total = cursor.fetchone()[0]
            print(f"✅  Added 'backup_weeks' (default=0) to {total} faculty records.")
        else:
            print("❌  Column was not added. Check database permissions.")
            return 1

        conn.close()
        return 0

    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("✅  Column already exists.")
            return 0
        print(f"❌  Database error: {e}")
        conn.rollback()
        conn.close()
        return 1


if __name__ == "__main__":
    print("=" * 60)
    print("FacultyHub Migration — Add backup_weeks to faculty")
    print("=" * 60)
    print()
    code = migrate()
    print()
    print("=" * 60)
    print("✅  Done." if code == 0 else "❌  Migration failed.")
    print("=" * 60)
    sys.exit(code)
