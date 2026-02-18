"""
Check the actual structure of wave_faculty_assignments table
"""

import sqlite3
import sys

def check_table(db_path="/data/moonlighter.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"Checking: {db_path}\n")

    # Get table info
    cursor.execute("PRAGMA table_info(wave_faculty_assignments)")
    columns = cursor.fetchall()

    print("wave_faculty_assignments columns:")
    print("-" * 60)
    for col in columns:
        print(f"  {col[1]:20s} {col[2]:15s} nullable={col[3]==0}")

    print()
    print("Has reminder_sent_at?", any(col[1] == 'reminder_sent_at' for col in columns))

    # Show a sample query
    print("\nRunning sample query...")
    try:
        cursor.execute("SELECT id, notified_at, reminder_sent_at FROM wave_faculty_assignments LIMIT 1")
        print("✅ Query succeeded - column exists and is accessible")
    except Exception as e:
        print(f"❌ Query failed: {e}")

    conn.close()

if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/data/moonlighter.db"
    check_table(db_path)
