"""
Add reminder_sent_at column to existing wave_faculty_assignments table
"""

import sqlite3
import sys

def add_reminder_column(db_path="/data/moonlighter.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(wave_faculty_assignments)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'reminder_sent_at' in columns:
            print("✅ Column 'reminder_sent_at' already exists!")
            return

        # Add the column
        print("Adding 'reminder_sent_at' column...")
        cursor.execute("""
            ALTER TABLE wave_faculty_assignments
            ADD COLUMN reminder_sent_at DATETIME
        """)

        conn.commit()
        print("✅ Column added successfully!")

    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/data/moonlighter.db"
    print(f"Database: {db_path}\n")
    add_reminder_column(db_path)
