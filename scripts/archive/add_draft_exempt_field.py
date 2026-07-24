#!/usr/bin/env python3
"""
Database migration: Add draft_exempt field to faculty table

This adds a boolean field to track faculty who do moonlighting
but should be excluded from the draft priority system.

Usage:
    python3 add_draft_exempt_field.py
"""

import sqlite3
from pathlib import Path
from datetime import datetime
import shutil


def find_database():
    """Find the database file"""
    possible_paths = [
        Path("./moonlighter.db"),
        Path("/data/moonlighter.db"),
        Path("../moonlighter.db"),
    ]

    for path in possible_paths:
        if path.exists():
            return path

    return None


def backup_database(db_path):
    """Create a backup of the database"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"{db_path.stem}.backup.{timestamp}.db"
    shutil.copy2(db_path, backup_path)
    return backup_path


def add_draft_exempt_field(db_path):
    """Add draft_exempt column to faculty table"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(faculty)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'draft_exempt' in columns:
            print("✅ Column 'draft_exempt' already exists in faculty table")
            return True

        print("📝 Adding 'draft_exempt' column to faculty table...")

        # Add the new column
        cursor.execute("""
            ALTER TABLE faculty
            ADD COLUMN draft_exempt BOOLEAN DEFAULT 0 NOT NULL
        """)

        conn.commit()

        print("✅ Successfully added 'draft_exempt' column")
        print()
        print("Field details:")
        print("  - Name: draft_exempt")
        print("  - Type: BOOLEAN")
        print("  - Default: 0 (False)")
        print("  - Nullable: NO")
        print()
        print("Purpose:")
        print("  Faculty who do moonlighting but should be excluded")
        print("  from the draft priority system can be flagged with")
        print("  draft_exempt = 1 (True)")

        return True

    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        conn.rollback()
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def verify_migration(db_path):
    """Verify the migration was successful"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check column exists and get its properties
        cursor.execute("PRAGMA table_info(faculty)")
        columns = {row[1]: row for row in cursor.fetchall()}

        if 'draft_exempt' not in columns:
            print("❌ Verification failed: Column not found")
            return False

        col_info = columns['draft_exempt']
        print()
        print("✅ Verification successful!")
        print(f"   Column: {col_info[1]}")
        print(f"   Type: {col_info[2]}")
        print(f"   Not Null: {bool(col_info[3])}")
        print(f"   Default: {col_info[4]}")

        # Count faculty with draft_exempt = 1
        cursor.execute("SELECT COUNT(*) FROM faculty WHERE draft_exempt = 1")
        exempt_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM faculty WHERE moonlighter = 1")
        moonlighter_count = cursor.fetchone()[0]

        print()
        print("Current status:")
        print(f"   Total moonlighters: {moonlighter_count}")
        print(f"   Draft exempt: {exempt_count}")

        return True

    except sqlite3.Error as e:
        print(f"❌ Verification error: {e}")
        return False
    finally:
        conn.close()


def main():
    print("=" * 70)
    print("Faculty Hub - Database Migration")
    print("Add draft_exempt field to faculty table")
    print("=" * 70)
    print()

    # Find database
    db_path = find_database()

    if not db_path:
        print("❌ Could not find database file!")
        print("\nSearched for:")
        print("  - ./moonlighter.db")
        print("  - /data/moonlighter.db")
        print("  - ../moonlighter.db")
        print()

        db_input = input("Enter database path (or press Enter to exit): ").strip()
        if db_input:
            db_path = Path(db_input)
            if not db_path.exists():
                print(f"❌ File not found: {db_path}")
                return
        else:
            return

    print(f"✅ Using database: {db_path}")
    print()

    # Create backup
    print("📦 Creating backup...")
    backup_path = backup_database(db_path)
    print(f"✅ Backup created: {backup_path}")
    print()

    # Add the field
    success = add_draft_exempt_field(db_path)

    if success:
        # Verify migration
        verify_migration(db_path)

        print()
        print("=" * 70)
        print("✅ Migration complete!")
        print("=" * 70)
        print()
        print("Next steps:")
        print("1. Restart your server if it's running")
        print("2. Use the admin panel to mark faculty as draft_exempt")
        print("3. When creating drafts, exempt faculty will be filtered out")
        print()
    else:
        print()
        print("=" * 70)
        print("❌ Migration failed")
        print("=" * 70)
        print(f"\nBackup available at: {backup_path}")
        print()


if __name__ == "__main__":
    main()
