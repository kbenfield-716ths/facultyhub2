#!/usr/bin/env python3
"""
Migration Script: Consolidate Faculty and Provider Models

This script migrates the dual Faculty/Provider structure to use only Faculty,
preserving all moonlighting signup and assignment data.

SAFETY:
- Creates complete backup before any changes
- Validates data integrity at each step
- Provides rollback instructions
- No data loss - all signups and assignments preserved
"""

import os
import sys
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))


class FacultyProviderMigration:
    """Safely consolidate Faculty and Provider models"""

    def __init__(self, db_path: str, test_mode: bool = True):
        self.db_path = Path(db_path)
        self.test_mode = test_mode
        self.backup_path = None

    def backup_database(self):
        """Create timestamped backup"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.backup_path = self.db_path.parent / f"{self.db_path.stem}_before_faculty_provider_merge_{timestamp}.db"

        print(f"Creating backup: {self.backup_path}")
        shutil.copy2(self.db_path, self.backup_path)
        print(f"✅ Backup created successfully")

        return self.backup_path

    def validate_preconditions(self):
        """Verify database is in expected state"""
        print("\nValidating preconditions...")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}

        required_tables = {'faculty', 'providers', 'signups', 'assignments'}
        missing = required_tables - tables

        if missing:
            print(f"❌ Missing required tables: {missing}")
            conn.close()
            return False

        # Get counts
        counts = {}
        for table in ['faculty', 'providers', 'signups', 'assignments']:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = cursor.fetchone()[0]

        print(f"  Faculty records: {counts['faculty']}")
        print(f"  Provider records: {counts['providers']}")
        print(f"  Signup records: {counts['signups']}")
        print(f"  Assignment records: {counts['assignments']}")

        # Check for orphaned providers
        cursor.execute("""
            SELECT COUNT(*) FROM providers p
            LEFT JOIN faculty f ON p.id = f.id
            WHERE f.id IS NULL
        """)
        orphaned_providers = cursor.fetchone()[0]

        if orphaned_providers > 0:
            print(f"  ⚠️  Found {orphaned_providers} providers without matching faculty records")
            print(f"      These will be skipped (signups/assignments will fail integrity check)")

        # Check foreign key integrity
        cursor.execute("""
            SELECT COUNT(*) FROM signups s
            LEFT JOIN providers p ON s.provider_id = p.id
            WHERE p.id IS NULL
        """)
        orphaned_signups = cursor.fetchone()[0]

        if orphaned_signups > 0:
            print(f"❌ Found {orphaned_signups} signups with invalid provider_id")
            conn.close()
            return False

        cursor.execute("""
            SELECT COUNT(*) FROM assignments a
            LEFT JOIN providers p ON a.provider_id = p.id
            WHERE p.id IS NULL
        """)
        orphaned_assignments = cursor.fetchone()[0]

        if orphaned_assignments > 0:
            print(f"❌ Found {orphaned_assignments} assignments with invalid provider_id")
            conn.close()
            return False

        conn.close()
        print("✅ Preconditions validated")
        return True

    def migrate_foreign_keys(self):
        """Update foreign key references from Provider to Faculty"""
        print("\nMigrating foreign key references...")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # SQLite doesn't support ALTER COLUMN, so we need to:
        # 1. Create new tables with updated foreign keys
        # 2. Copy data
        # 3. Drop old tables
        # 4. Rename new tables

        print("  Creating new signups table...")
        cursor.execute("""
            CREATE TABLE signups_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id TEXT NOT NULL,
                shift_id INTEGER NOT NULL,
                desired_nights INTEGER NOT NULL,
                locked BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (provider_id) REFERENCES faculty(id),
                FOREIGN KEY (shift_id) REFERENCES shifts(id)
            )
        """)

        cursor.execute("""
            CREATE INDEX ix_signups_new_provider_id ON signups_new (provider_id)
        """)

        cursor.execute("""
            CREATE INDEX ix_signups_new_shift_id ON signups_new (shift_id)
        """)

        print("  Copying signup data...")
        cursor.execute("""
            INSERT INTO signups_new (id, provider_id, shift_id, desired_nights, locked, created_at)
            SELECT id, provider_id, shift_id, desired_nights, locked, created_at
            FROM signups
        """)

        signups_copied = cursor.rowcount
        print(f"    ✅ Copied {signups_copied} signups")

        print("  Creating new assignments table...")
        cursor.execute("""
            CREATE TABLE assignments_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id TEXT NOT NULL,
                shift_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (provider_id) REFERENCES faculty(id),
                FOREIGN KEY (shift_id) REFERENCES shifts(id)
            )
        """)

        print("  Copying assignment data...")
        cursor.execute("""
            INSERT INTO assignments_new (id, provider_id, shift_id, created_at)
            SELECT id, provider_id, shift_id, created_at
            FROM assignments
        """)

        assignments_copied = cursor.rowcount
        print(f"    ✅ Copied {assignments_copied} assignments")

        # Drop old tables and rename new ones
        print("  Swapping tables...")
        cursor.execute("DROP TABLE signups")
        cursor.execute("ALTER TABLE signups_new RENAME TO signups")

        cursor.execute("DROP TABLE assignments")
        cursor.execute("ALTER TABLE assignments_new RENAME TO assignments")

        conn.commit()
        conn.close()

        print("✅ Foreign keys migrated successfully")
        return True

    def remove_provider_table(self):
        """Remove the Provider table (now redundant)"""
        print("\nRemoving Provider table...")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("DROP TABLE IF EXISTS providers")

        conn.commit()
        conn.close()

        print("✅ Provider table removed")

    def validate_migration(self):
        """Verify data integrity after migration"""
        print("\nValidating migration...")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}

        if 'providers' in tables:
            print("❌ Provider table still exists")
            conn.close()
            return False

        # Check record counts
        cursor.execute("SELECT COUNT(*) FROM signups")
        signups_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM assignments")
        assignments_count = cursor.fetchone()[0]

        print(f"  Signups: {signups_count}")
        print(f"  Assignments: {assignments_count}")

        # Verify all signups reference valid faculty
        cursor.execute("""
            SELECT COUNT(*) FROM signups s
            LEFT JOIN faculty f ON s.provider_id = f.id
            WHERE f.id IS NULL
        """)
        invalid_signups = cursor.fetchone()[0]

        if invalid_signups > 0:
            print(f"❌ Found {invalid_signups} signups with invalid faculty reference")
            conn.close()
            return False

        # Verify all assignments reference valid faculty
        cursor.execute("""
            SELECT COUNT(*) FROM assignments a
            LEFT JOIN faculty f ON a.provider_id = f.id
            WHERE f.id IS NULL
        """)
        invalid_assignments = cursor.fetchone()[0]

        if invalid_assignments > 0:
            print(f"❌ Found {invalid_assignments} assignments with invalid faculty reference")
            conn.close()
            return False

        conn.close()
        print("✅ Migration validated successfully")
        return True

    def run(self):
        """Execute full migration"""
        print("=" * 70)
        print("FACULTY/PROVIDER CONSOLIDATION MIGRATION")
        print("=" * 70)
        print()
        print(f"Database: {self.db_path}")
        print(f"Test mode: {self.test_mode}")
        print()

        # Step 1: Backup
        self.backup_database()

        # Step 2: Validate preconditions
        if not self.validate_preconditions():
            print("\n❌ Precondition validation failed. Migration aborted.")
            print(f"Backup preserved at: {self.backup_path}")
            return False

        if self.test_mode:
            print("\n" + "=" * 70)
            print("TEST MODE: Review changes above")
            print("=" * 70)
            response = input("Proceed with migration? (yes/no): ")
            if response.lower() != "yes":
                print("Migration cancelled.")
                print(f"Backup preserved at: {self.backup_path}")
                return False

        # Step 3: Migrate foreign keys
        if not self.migrate_foreign_keys():
            print("\n❌ Foreign key migration failed.")
            print(f"Restore from backup: cp {self.backup_path} {self.db_path}")
            return False

        # Step 4: Remove Provider table
        self.remove_provider_table()

        # Step 5: Validate
        if not self.validate_migration():
            print("\n❌ Validation failed after migration.")
            print(f"Restore from backup: cp {self.backup_path} {self.db_path}")
            return False

        print("\n" + "=" * 70)
        print("✅ MIGRATION COMPLETED SUCCESSFULLY")
        print("=" * 70)
        print()
        print("NEXT STEPS:")
        print()
        print("1. Update backend/models.py:")
        print("   - Remove Provider class (lines 166-176)")
        print("   - Update Signup.provider relationship to reference Faculty")
        print("   - Update Assignment.provider relationship to reference Faculty")
        print()
        print("2. Remove sync utilities:")
        print("   - Delete backend/sync_utils.py")
        print("   - Remove sync imports from backend/app.py")
        print("   - Remove sync calls from signup endpoint")
        print()
        print("3. Update app.py imports:")
        print("   - Remove Provider from models import")
        print("   - Remove sync_provider_from_faculty, sync_all_providers_from_faculty")
        print()
        print("4. Test moonlighting features:")
        print("   - Submit signup")
        print("   - Run optimizer")
        print("   - View assignments")
        print()
        print(f"Backup preserved at: {self.backup_path}")
        print()
        print("ROLLBACK:")
        print(f"  cp {self.backup_path} {self.db_path}")
        print("  git checkout backend/models.py backend/app.py")
        print()

        return True


def main():
    """Run migration"""
    import argparse

    parser = argparse.ArgumentParser(description="Consolidate Faculty and Provider models")
    parser.add_argument(
        "--database",
        default="moonlighter.db",
        help="Path to database file (default: moonlighter.db)"
    )
    parser.add_argument(
        "--no-test",
        action="store_true",
        help="Skip test mode confirmation (USE WITH CAUTION)"
    )

    args = parser.parse_args()

    db_path = Path(args.database)
    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        print("Specify path with --database flag")
        return 1

    test_mode = not args.no_test

    migrator = FacultyProviderMigration(db_path, test_mode=test_mode)
    success = migrator.run()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
