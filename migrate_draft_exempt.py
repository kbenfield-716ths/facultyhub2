#!/usr/bin/env python3
"""
Simple migration script to add draft_exempt column to faculty table
Can be run on Fly.io as: python3 migrate_draft_exempt.py
"""

import sqlite3
import sys
import os

def find_database():
    """Find the database file"""
    possible_paths = [
        '/data/moonlighter.db',
        '/app/moonlighter.db',
        './moonlighter.db',
        'moonlighter.db',
        '../moonlighter.db'
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    return None

def migrate():
    """Add draft_exempt column to faculty table"""

    # Find database
    db_path = find_database()

    if not db_path:
        print("❌ ERROR: Could not find database file!")
        print("Searched paths:")
        print("  - /data/moonlighter.db")
        print("  - /app/moonlighter.db")
        print("  - ./moonlighter.db")
        sys.exit(1)

    print(f"✅ Found database: {db_path}")

    # Connect to database
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if column already exists
        cursor.execute("PRAGMA table_info(faculty)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'draft_exempt' in columns:
            print("✅ Column 'draft_exempt' already exists - migration not needed")
            conn.close()
            return 0

        # Add the column
        print("📝 Adding draft_exempt column...")
        cursor.execute("""
            ALTER TABLE faculty
            ADD COLUMN draft_exempt BOOLEAN DEFAULT 0 NOT NULL
        """)

        conn.commit()

        # Verify it was added
        cursor.execute("PRAGMA table_info(faculty)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'draft_exempt' in columns:
            print("✅ Successfully added draft_exempt column!")

            # Show current stats
            cursor.execute("SELECT COUNT(*) FROM faculty WHERE draft_exempt = 1")
            exempt_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM faculty WHERE moonlighter = 1")
            moonlighter_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM faculty")
            total_count = cursor.fetchone()[0]

            print(f"\n📊 Current Status:")
            print(f"   Total faculty: {total_count}")
            print(f"   Moonlighters: {moonlighter_count}")
            print(f"   Draft exempt: {exempt_count}")

            conn.close()
            return 0
        else:
            print("❌ ERROR: Column was not added successfully")
            conn.close()
            return 1

    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("✅ Column already exists")
            return 0
        else:
            print(f"❌ Database error: {e}")
            return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    print("=" * 70)
    print("Faculty Hub - Database Migration")
    print("Add draft_exempt field to faculty table")
    print("=" * 70)
    print()

    exit_code = migrate()

    print()
    print("=" * 70)
    if exit_code == 0:
        print("✅ Migration completed successfully!")
    else:
        print("❌ Migration failed!")
    print("=" * 70)

    sys.exit(exit_code)
