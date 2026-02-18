"""
Migration: Add reminder_sent_at column to wave_faculty_assignments table
Run this after deploying the model change
"""

import sqlite3
import sys

def migrate(db_path="facultyhub.db"):
    """Add reminder_sent_at column to wave_faculty_assignments"""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(wave_faculty_assignments)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'reminder_sent_at' in columns:
            print("✅ Column 'reminder_sent_at' already exists - skipping migration")
            return

        # Add the new column
        print("Adding 'reminder_sent_at' column to wave_faculty_assignments...")
        cursor.execute("""
            ALTER TABLE wave_faculty_assignments
            ADD COLUMN reminder_sent_at DATETIME
        """)

        conn.commit()
        print("✅ Migration completed successfully!")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/data/facultyhub.db"
    print(f"Migrating database: {db_path}")
    migrate(db_path)
