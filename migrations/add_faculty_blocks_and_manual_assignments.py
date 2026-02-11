"""
Migration: Add Faculty Blocks and Manual Assignment Tracking

This migration adds:
1. faculty_blocks table for blocking faculty from specific weeks
2. is_manual, reason, and created_by columns to service_week_assignments

Run this script once to upgrade the database schema.
"""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path to import models
sys.path.insert(0, str(Path(__file__).parent.parent))

def run_migration(db_path: str = "/data/moonlighter.db"):
    """Run the migration to add faculty blocks and manual assignment tracking"""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("🔄 Starting migration: Add faculty blocks and manual assignment tracking")

    try:
        # ==================== CHECK IF ALREADY MIGRATED ====================

        # Check if faculty_blocks table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='faculty_blocks'
        """)
        blocks_table_exists = cursor.fetchone() is not None

        # Check if is_manual column exists in service_week_assignments
        cursor.execute("PRAGMA table_info(service_week_assignments)")
        columns = [row[1] for row in cursor.fetchall()]
        is_manual_exists = 'is_manual' in columns

        if blocks_table_exists and is_manual_exists:
            print("✅ Migration already applied. Skipping.")
            conn.close()
            return

        # ==================== CREATE FACULTY_BLOCKS TABLE ====================

        if not blocks_table_exists:
            print("📝 Creating faculty_blocks table...")
            cursor.execute("""
                CREATE TABLE faculty_blocks (
                    id TEXT PRIMARY KEY,
                    faculty_id TEXT NOT NULL,
                    week_id TEXT NOT NULL,
                    reason TEXT,
                    created_by TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (faculty_id) REFERENCES faculty (id),
                    FOREIGN KEY (week_id) REFERENCES service_weeks (id),
                    FOREIGN KEY (created_by) REFERENCES faculty (id)
                )
            """)

            # Create indexes for better query performance
            cursor.execute("""
                CREATE INDEX idx_faculty_blocks_faculty_id
                ON faculty_blocks(faculty_id)
            """)
            cursor.execute("""
                CREATE INDEX idx_faculty_blocks_week_id
                ON faculty_blocks(week_id)
            """)

            print("✅ faculty_blocks table created")
        else:
            print("⏭️  faculty_blocks table already exists")

        # ==================== ADD COLUMNS TO SERVICE_WEEK_ASSIGNMENTS ====================

        if not is_manual_exists:
            print("📝 Adding is_manual, reason, and created_by columns to service_week_assignments...")

            # Add is_manual column
            cursor.execute("""
                ALTER TABLE service_week_assignments
                ADD COLUMN is_manual BOOLEAN DEFAULT 0
            """)

            # Add reason column
            cursor.execute("""
                ALTER TABLE service_week_assignments
                ADD COLUMN reason TEXT
            """)

            # Add created_by column
            cursor.execute("""
                ALTER TABLE service_week_assignments
                ADD COLUMN created_by TEXT
            """)

            print("✅ Columns added to service_week_assignments")
        else:
            print("⏭️  service_week_assignments already has manual assignment columns")

        # ==================== COMMIT CHANGES ====================

        conn.commit()
        print("✅ Migration completed successfully!")

        # ==================== VERIFY ====================

        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='faculty_blocks'")
        blocks_count = cursor.fetchone()[0]

        cursor.execute("PRAGMA table_info(service_week_assignments)")
        swa_columns = [row[1] for row in cursor.fetchall()]

        print("\n📊 Verification:")
        print(f"   - faculty_blocks table: {'✅ exists' if blocks_count == 1 else '❌ missing'}")
        print(f"   - is_manual column: {'✅ exists' if 'is_manual' in swa_columns else '❌ missing'}")
        print(f"   - reason column: {'✅ exists' if 'reason' in swa_columns else '❌ missing'}")
        print(f"   - created_by column: {'✅ exists' if 'created_by' in swa_columns else '❌ missing'}")

    except Exception as e:
        print(f"❌ Error during migration: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Add faculty blocks and manual assignment tracking')
    parser.add_argument('--db', default='/data/moonlighter.db',
                       help='Path to SQLite database (default: /data/moonlighter.db)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Check if migration is needed without applying it')

    args = parser.parse_args()

    if args.dry_run:
        print("🔍 Dry run mode - checking migration status...")
        conn = sqlite3.connect(args.db)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='faculty_blocks'")
        blocks_exists = cursor.fetchone() is not None

        cursor.execute("PRAGMA table_info(service_week_assignments)")
        columns = [row[1] for row in cursor.fetchall()]
        is_manual_exists = 'is_manual' in columns

        if blocks_exists and is_manual_exists:
            print("✅ Migration already applied")
        else:
            print("⚠️  Migration needed:")
            if not blocks_exists:
                print("   - faculty_blocks table missing")
            if not is_manual_exists:
                print("   - manual assignment columns missing from service_week_assignments")

        conn.close()
    else:
        run_migration(args.db)
