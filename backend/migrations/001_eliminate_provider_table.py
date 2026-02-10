"""
Migration 001: Eliminate Provider Table
Merges Provider functionality into Faculty table.

This migration:
1. Verifies all providers exist in faculty table
2. Updates foreign keys in Signup and Assignment tables
3. Marks faculty as moonlighters
4. Drops Provider table
5. Creates comprehensive backup before any changes

Rollback: See 001_rollback_restore_provider.py
"""

import sqlite3
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class MigrationError(Exception):
    """Custom exception for migration failures"""
    pass


def get_db_path():
    """Get the database path"""
    # Check if running in Fly.io or local
    if os.path.exists('/app/moonlighter.db'):
        return '/app/moonlighter.db'
    elif os.path.exists('moonlighter.db'):
        return 'moonlighter.db'
    elif os.path.exists('../moonlighter.db'):
        return '../moonlighter.db'
    else:
        raise MigrationError("Cannot find moonlighter.db")


def backup_database(db_path):
    """Create timestamped backup of database"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{db_path}.backup_before_001_{timestamp}"

    print(f"📦 Creating backup: {backup_path}")

    try:
        # Use SQLite backup command
        conn = sqlite3.connect(db_path)
        backup_conn = sqlite3.connect(backup_path)

        conn.backup(backup_conn)

        backup_conn.close()
        conn.close()

        print(f"✅ Backup created successfully")
        return backup_path

    except Exception as e:
        print(f"❌ Backup failed: {e}")
        raise MigrationError(f"Backup failed: {e}")


def verify_preconditions(conn):
    """Verify system is ready for migration"""
    print("\n🔍 Verifying preconditions...")

    cursor = conn.cursor()
    issues = []

    # Check 1: Provider table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='providers'")
    if not cursor.fetchone():
        issues.append("Provider table does not exist")

    # Check 2: Faculty table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='faculty'")
    if not cursor.fetchone():
        issues.append("Faculty table does not exist")

    if issues:
        return False, issues

    # Check 3: All provider_ids in signups exist in faculty
    cursor.execute("""
        SELECT DISTINCT s.provider_id
        FROM signups s
        LEFT JOIN faculty f ON s.provider_id = f.id
        WHERE f.id IS NULL
    """)
    orphaned_signups = cursor.fetchall()
    if orphaned_signups:
        issues.append(f"Found {len(orphaned_signups)} signups with provider_ids not in faculty table: {orphaned_signups}")

    # Check 4: All provider_ids in assignments exist in faculty
    cursor.execute("""
        SELECT DISTINCT a.provider_id
        FROM assignments a
        LEFT JOIN faculty f ON a.provider_id = f.id
        WHERE f.id IS NULL
    """)
    orphaned_assignments = cursor.fetchall()
    if orphaned_assignments:
        issues.append(f"Found {len(orphaned_assignments)} assignments with provider_ids not in faculty table: {orphaned_assignments}")

    # Check 5: Get counts for verification
    cursor.execute("SELECT COUNT(*) FROM providers")
    provider_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM faculty")
    faculty_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM signups")
    signup_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM assignments")
    assignment_count = cursor.fetchone()[0]

    print(f"📊 Current state:")
    print(f"   - Providers: {provider_count}")
    print(f"   - Faculty: {faculty_count}")
    print(f"   - Signups: {signup_count}")
    print(f"   - Assignments: {assignment_count}")

    if issues:
        return False, issues

    return True, {
        'provider_count': provider_count,
        'faculty_count': faculty_count,
        'signup_count': signup_count,
        'assignment_count': assignment_count
    }


def sync_providers_to_faculty(conn):
    """Ensure all providers exist in faculty table with moonlighter flag"""
    print("\n🔄 Syncing providers to faculty...")

    cursor = conn.cursor()

    # Find providers not in faculty
    cursor.execute("""
        SELECT p.id, p.name, p.email
        FROM providers p
        LEFT JOIN faculty f ON p.id = f.id
        WHERE f.id IS NULL
    """)
    missing_providers = cursor.fetchall()

    if missing_providers:
        print(f"   Found {len(missing_providers)} providers not in faculty table")
        print(f"   Creating faculty records for: {[p[0] for p in missing_providers]}")

        for provider_id, name, email in missing_providers:
            cursor.execute("""
                INSERT INTO faculty (
                    id, name, email, rank, clinical_effort_pct,
                    base_points, bonus_points, active, moonlighter,
                    registered, is_admin, password_changed,
                    micu_weeks, app_icu_weeks, procedure_weeks, consult_weeks
                ) VALUES (?, ?, ?, 'assistant', 100, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0)
            """, (provider_id, name, email or ''))

        print(f"   ✅ Created {len(missing_providers)} faculty records")
    else:
        print("   ✅ All providers already exist in faculty table")

    # Mark all providers as moonlighters in faculty table
    cursor.execute("""
        UPDATE faculty
        SET moonlighter = 1
        WHERE id IN (SELECT id FROM providers)
    """)

    marked_count = cursor.rowcount
    print(f"   ✅ Marked {marked_count} faculty as moonlighters")

    conn.commit()


def update_foreign_keys(conn):
    """Update foreign key constraints to point to faculty table"""
    print("\n🔗 Updating foreign key constraints...")

    cursor = conn.cursor()

    # SQLite doesn't support ALTER TABLE DROP/ADD CONSTRAINT directly
    # We need to recreate the tables

    # Step 1: Get current signups data
    cursor.execute("SELECT * FROM signups")
    signups_data = cursor.fetchall()
    print(f"   📋 Backed up {len(signups_data)} signups")

    # Step 2: Get current assignments data
    cursor.execute("SELECT * FROM assignments")
    assignments_data = cursor.fetchall()
    print(f"   📋 Backed up {len(assignments_data)} assignments")

    # Step 3: Get table schemas
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='signups'")
    signups_schema = cursor.fetchone()[0]

    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='assignments'")
    assignments_schema = cursor.fetchone()[0]

    # Step 4: Create new signups table with updated foreign key
    print("   🔄 Recreating signups table...")
    cursor.execute("DROP TABLE IF EXISTS signups_new")

    # Updated schema pointing to faculty
    new_signups_schema = signups_schema.replace(
        'FOREIGN KEY(provider_id) REFERENCES providers(id)',
        'FOREIGN KEY(provider_id) REFERENCES faculty(id)'
    )

    cursor.execute(new_signups_schema.replace('CREATE TABLE signups', 'CREATE TABLE signups_new'))

    # Copy data
    if signups_data:
        placeholders = ','.join(['?' for _ in signups_data[0]])
        cursor.executemany(f"INSERT INTO signups_new VALUES ({placeholders})", signups_data)

    # Step 5: Create new assignments table with updated foreign key
    print("   🔄 Recreating assignments table...")
    cursor.execute("DROP TABLE IF EXISTS assignments_new")

    new_assignments_schema = assignments_schema.replace(
        'FOREIGN KEY(provider_id) REFERENCES providers(id)',
        'FOREIGN KEY(provider_id) REFERENCES faculty(id)'
    )

    cursor.execute(new_assignments_schema.replace('CREATE TABLE assignments', 'CREATE TABLE assignments_new'))

    # Copy data
    if assignments_data:
        placeholders = ','.join(['?' for _ in assignments_data[0]])
        cursor.executemany(f"INSERT INTO assignments_new VALUES ({placeholders})", assignments_data)

    # Step 6: Swap tables
    print("   🔄 Swapping tables...")
    cursor.execute("DROP TABLE signups")
    cursor.execute("ALTER TABLE signups_new RENAME TO signups")

    cursor.execute("DROP TABLE assignments")
    cursor.execute("ALTER TABLE assignments_new RENAME TO assignments")

    conn.commit()
    print("   ✅ Foreign keys updated successfully")


def drop_provider_table(conn):
    """Drop the Provider table"""
    print("\n🗑️  Dropping Provider table...")

    cursor = conn.cursor()

    # Final verification - make sure no foreign keys reference providers
    cursor.execute("""
        SELECT sql FROM sqlite_master
        WHERE sql LIKE '%providers%'
        AND type = 'table'
        AND name != 'providers'
    """)

    references = cursor.fetchall()
    if references:
        print("   ⚠️  Warning: Found tables still referencing providers:")
        for ref in references:
            print(f"      {ref[0]}")
        raise MigrationError("Cannot drop providers table - still referenced")

    # Drop the table
    cursor.execute("DROP TABLE providers")
    conn.commit()

    print("   ✅ Provider table dropped successfully")


def verify_postconditions(conn, pre_state):
    """Verify migration succeeded"""
    print("\n✅ Verifying postconditions...")

    cursor = conn.cursor()
    issues = []

    # Check 1: Provider table should not exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='providers'")
    if cursor.fetchone():
        issues.append("Provider table still exists")

    # Check 2: Verify signup count unchanged
    cursor.execute("SELECT COUNT(*) FROM signups")
    signup_count = cursor.fetchone()[0]
    if signup_count != pre_state['signup_count']:
        issues.append(f"Signup count changed: {pre_state['signup_count']} -> {signup_count}")

    # Check 3: Verify assignment count unchanged
    cursor.execute("SELECT COUNT(*) FROM assignments")
    assignment_count = cursor.fetchone()[0]
    if assignment_count != pre_state['assignment_count']:
        issues.append(f"Assignment count changed: {pre_state['assignment_count']} -> {assignment_count}")

    # Check 4: Verify all moonlighters set
    cursor.execute("SELECT COUNT(*) FROM faculty WHERE moonlighter = 1")
    moonlighter_count = cursor.fetchone()[0]
    if moonlighter_count < pre_state['provider_count']:
        issues.append(f"Not all providers marked as moonlighters: expected {pre_state['provider_count']}, got {moonlighter_count}")

    # Check 5: Verify foreign keys work
    cursor.execute("""
        SELECT COUNT(*)
        FROM signups s
        JOIN faculty f ON s.provider_id = f.id
    """)
    valid_signups = cursor.fetchone()[0]
    if valid_signups != signup_count:
        issues.append(f"Foreign key issue in signups: {valid_signups}/{signup_count} valid")

    cursor.execute("""
        SELECT COUNT(*)
        FROM assignments a
        JOIN faculty f ON a.provider_id = f.id
    """)
    valid_assignments = cursor.fetchone()[0]
    if valid_assignments != assignment_count:
        issues.append(f"Foreign key issue in assignments: {valid_assignments}/{assignment_count} valid")

    if issues:
        return False, issues

    print(f"📊 Post-migration state:")
    print(f"   - Signups: {signup_count} (unchanged)")
    print(f"   - Assignments: {assignment_count} (unchanged)")
    print(f"   - Moonlighters: {moonlighter_count}")
    print(f"   - Provider table: REMOVED ✅")

    return True, None


def run_migration(db_path=None):
    """Execute the full migration"""
    print("=" * 60)
    print("🚀 Starting Migration 001: Eliminate Provider Table")
    print("=" * 60)

    if not db_path:
        db_path = get_db_path()

    print(f"📂 Database: {db_path}")

    # Step 1: Backup
    try:
        backup_path = backup_database(db_path)
    except Exception as e:
        print(f"\n❌ MIGRATION ABORTED: Backup failed")
        print(f"   Error: {e}")
        return False

    # Step 2: Connect
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = OFF")  # Temporarily disable for migration
    except Exception as e:
        print(f"\n❌ MIGRATION ABORTED: Cannot connect to database")
        print(f"   Error: {e}")
        return False

    try:
        # Step 3: Verify preconditions
        success, result = verify_preconditions(conn)
        if not success:
            print(f"\n❌ MIGRATION ABORTED: Preconditions not met")
            for issue in result:
                print(f"   - {issue}")
            conn.close()
            return False

        pre_state = result

        # Step 4: Sync providers to faculty
        sync_providers_to_faculty(conn)

        # Step 5: Update foreign keys
        update_foreign_keys(conn)

        # Step 6: Drop provider table
        drop_provider_table(conn)

        # Step 7: Re-enable foreign keys
        conn.execute("PRAGMA foreign_keys = ON")

        # Step 8: Verify postconditions
        success, issues = verify_postconditions(conn, pre_state)
        if not success:
            print(f"\n❌ MIGRATION FAILED: Postconditions not met")
            for issue in issues:
                print(f"   - {issue}")
            print(f"\n🔄 ROLLBACK: Restore from backup: {backup_path}")
            conn.close()
            return False

        conn.close()

        print("\n" + "=" * 60)
        print("✅ MIGRATION 001 COMPLETED SUCCESSFULLY")
        print("=" * 60)
        print(f"📦 Backup saved at: {backup_path}")
        print(f"🗑️  Provider table eliminated")
        print(f"✅ All data migrated to Faculty table")
        print(f"✅ Foreign keys updated")
        print(f"✅ Data integrity verified")

        return True

    except Exception as e:
        print(f"\n❌ MIGRATION FAILED WITH ERROR:")
        print(f"   {type(e).__name__}: {e}")
        print(f"\n🔄 ROLLBACK REQUIRED:")
        print(f"   1. Stop application")
        print(f"   2. Restore backup: {backup_path}")
        print(f"   3. Restart application")

        try:
            conn.close()
        except:
            pass

        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Eliminate Provider Table Migration')
    parser.add_argument('--db', help='Path to database file', default=None)
    parser.add_argument('--dry-run', action='store_true', help='Verify preconditions only')

    args = parser.parse_args()

    if args.dry_run:
        print("🔍 DRY RUN MODE - Verification only")
        db_path = args.db or get_db_path()
        conn = sqlite3.connect(db_path)
        success, result = verify_preconditions(conn)
        conn.close()

        if success:
            print("\n✅ All preconditions met - ready to migrate")
            sys.exit(0)
        else:
            print("\n❌ Preconditions not met:")
            for issue in result:
                print(f"   - {issue}")
            sys.exit(1)
    else:
        success = run_migration(args.db)
        sys.exit(0 if success else 1)
