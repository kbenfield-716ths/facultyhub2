"""
Initialize Wave Draft System Tables
Creates all required tables and adds reminder_sent_at column
"""

import sqlite3
import sys

def init_wave_draft_tables(db_path="facultyhub.db"):
    """Create wave draft tables and add reminder_sent_at column"""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        print("Initializing Wave Draft System tables...")

        # 1. Create draft_wave_configs table
        print("  Creating draft_wave_configs...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS draft_wave_configs (
                id TEXT PRIMARY KEY,
                year INTEGER NOT NULL UNIQUE,
                close_date DATETIME NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at DATETIME,
                activated_at DATETIME,
                closed_at DATETIME
            )
        """)

        # 2. Create draft_waves table
        print("  Creating draft_waves...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS draft_waves (
                id TEXT PRIMARY KEY,
                config_id TEXT NOT NULL,
                name TEXT NOT NULL,
                open_date DATETIME NOT NULL,
                wave_order INTEGER NOT NULL,
                FOREIGN KEY (config_id) REFERENCES draft_wave_configs(id)
            )
        """)

        # 3. Create wave_faculty_assignments table
        print("  Creating wave_faculty_assignments...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS wave_faculty_assignments (
                id TEXT PRIMARY KEY,
                wave_id TEXT NOT NULL,
                faculty_id TEXT NOT NULL,
                notified_at DATETIME,
                reminder_sent_at DATETIME,
                created_at DATETIME,
                FOREIGN KEY (wave_id) REFERENCES draft_waves(id),
                FOREIGN KEY (faculty_id) REFERENCES faculty(id)
            )
        """)

        # 4. Create unique index
        print("  Creating wave_faculty_assignments index...")
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_wave_faculty_unique
            ON wave_faculty_assignments(wave_id, faculty_id)
        """)

        # 5. Create week_draft_status table
        print("  Creating week_draft_status...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS week_draft_status (
                id TEXT PRIMARY KEY,
                config_id TEXT NOT NULL,
                week_id TEXT NOT NULL,
                unavailable_count INTEGER DEFAULT 0,
                volunteer_count INTEGER DEFAULT 0,
                FOREIGN KEY (config_id) REFERENCES draft_wave_configs(id),
                FOREIGN KEY (week_id) REFERENCES service_weeks(id)
            )
        """)

        # 6. Create draft_week_requests table
        print("  Creating draft_week_requests...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS draft_week_requests (
                id TEXT PRIMARY KEY,
                config_id TEXT NOT NULL,
                faculty_id TEXT NOT NULL,
                week_id TEXT NOT NULL,
                request_type TEXT NOT NULL,
                created_at DATETIME,
                FOREIGN KEY (config_id) REFERENCES draft_wave_configs(id),
                FOREIGN KEY (faculty_id) REFERENCES faculty(id),
                FOREIGN KEY (week_id) REFERENCES service_weeks(id)
            )
        """)

        # 7. Check if reminder_sent_at already exists (for existing deployments)
        cursor.execute("PRAGMA table_info(wave_faculty_assignments)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'reminder_sent_at' not in columns:
            print("  Adding reminder_sent_at column...")
            cursor.execute("""
                ALTER TABLE wave_faculty_assignments
                ADD COLUMN reminder_sent_at DATETIME
            """)
        else:
            print("  ✓ reminder_sent_at column already exists")

        conn.commit()
        print("✅ Wave Draft System initialized successfully!")
        print()
        print("Tables created:")
        print("  - draft_wave_configs")
        print("  - draft_waves")
        print("  - wave_faculty_assignments (with reminder_sent_at)")
        print("  - week_draft_status")
        print("  - draft_week_requests")

    except Exception as e:
        print(f"❌ Initialization failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/data/staff.db"
    print(f"Database: {db_path}")
    print()
    init_wave_draft_tables(db_path)
