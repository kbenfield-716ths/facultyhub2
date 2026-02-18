"""
Rebuild wave draft tables from scratch using schema that exactly matches SQLAlchemy models.
Run this when tables need to be recreated (e.g. schema mismatch after failed migration).
"""

import sqlite3
import sys

def rebuild_tables(db_path="/data/moonlighter.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"Rebuilding wave draft tables in: {db_path}\n")

    try:
        # Drop all wave draft tables in correct order (respecting foreign keys)
        print("Dropping old tables...")
        cursor.execute("DROP TABLE IF EXISTS draft_week_requests")
        cursor.execute("DROP TABLE IF EXISTS week_draft_status")
        cursor.execute("DROP TABLE IF EXISTS wave_faculty_assignments")
        cursor.execute("DROP TABLE IF EXISTS draft_waves")
        cursor.execute("DROP TABLE IF EXISTS draft_wave_configs")
        print("  ✅ Old tables dropped")

        # Recreate tables with schema matching backend/models.py exactly
        print("\nCreating fresh tables...")

        # DraftWaveConfig model: id, year, close_date, status, created_at, activated_at, closed_at
        cursor.execute("""
            CREATE TABLE draft_wave_configs (
                id TEXT PRIMARY KEY,
                year INTEGER NOT NULL UNIQUE,
                close_date DATETIME NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at DATETIME,
                activated_at DATETIME,
                closed_at DATETIME
            )
        """)
        print("  ✅ draft_wave_configs")

        # DraftWave model: id, config_id, name, open_date, wave_order, created_at
        cursor.execute("""
            CREATE TABLE draft_waves (
                id TEXT PRIMARY KEY,
                config_id TEXT NOT NULL,
                name TEXT NOT NULL,
                open_date DATETIME NOT NULL,
                wave_order INTEGER NOT NULL,
                created_at DATETIME,
                FOREIGN KEY (config_id) REFERENCES draft_wave_configs(id)
            )
        """)
        print("  ✅ draft_waves (with created_at)")

        # WaveFacultyAssignment model: id, wave_id, faculty_id, notified_at, reminder_sent_at, created_at
        cursor.execute("""
            CREATE TABLE wave_faculty_assignments (
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
        cursor.execute("""
            CREATE UNIQUE INDEX idx_wave_faculty_unique
            ON wave_faculty_assignments(wave_id, faculty_id)
        """)
        print("  ✅ wave_faculty_assignments (with reminder_sent_at + unique index)")

        # WeekDraftStatus model: id, config_id, week_id, unavailable_count, volunteer_count, updated_at
        cursor.execute("""
            CREATE TABLE week_draft_status (
                id TEXT PRIMARY KEY,
                config_id TEXT NOT NULL,
                week_id TEXT NOT NULL,
                unavailable_count INTEGER DEFAULT 0,
                volunteer_count INTEGER DEFAULT 0,
                updated_at DATETIME,
                FOREIGN KEY (config_id) REFERENCES draft_wave_configs(id),
                FOREIGN KEY (week_id) REFERENCES service_weeks(id)
            )
        """)
        cursor.execute("""
            CREATE UNIQUE INDEX idx_week_status_config_week
            ON week_draft_status(config_id, week_id)
        """)
        print("  ✅ week_draft_status (with updated_at + unique index)")

        # DraftWeekRequest model: id, config_id, faculty_id, week_id, request_type, submitted_at
        cursor.execute("""
            CREATE TABLE draft_week_requests (
                id TEXT PRIMARY KEY,
                config_id TEXT NOT NULL,
                faculty_id TEXT NOT NULL,
                week_id TEXT NOT NULL,
                request_type TEXT NOT NULL,
                submitted_at DATETIME,
                FOREIGN KEY (config_id) REFERENCES draft_wave_configs(id),
                FOREIGN KEY (faculty_id) REFERENCES faculty(id),
                FOREIGN KEY (week_id) REFERENCES service_weeks(id)
            )
        """)
        cursor.execute("""
            CREATE INDEX idx_draft_request_faculty_week
            ON draft_week_requests(faculty_id, week_id)
        """)
        cursor.execute("""
            CREATE INDEX idx_draft_request_config
            ON draft_week_requests(config_id)
        """)
        print("  ✅ draft_week_requests (with submitted_at + 2 indexes)")

        conn.commit()
        print("\n✅ All wave draft tables rebuilt successfully!")
        print("\nSchema matches backend/models.py exactly.")
        print("\nTables created:")
        print("  - draft_wave_configs")
        print("  - draft_waves (created_at)")
        print("  - wave_faculty_assignments (reminder_sent_at, created_at)")
        print("  - week_draft_status (updated_at)")
        print("  - draft_week_requests (submitted_at)")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/data/moonlighter.db"

    print("⚠️  WARNING: This will delete any existing wave draft data!")
    print(f"Database: {db_path}")
    print("Press Ctrl+C to cancel, or Enter to continue...")
    input()

    rebuild_tables(db_path)
