"""
Rollback for Migration 001: Restore Provider Table

This script can recreate the Provider table from Faculty data
if the migration needs to be rolled back.

SAFER OPTION: Just restore from the backup file created before migration:
    mv staff.db moonlighter_failed.db
    cp staff.db.backup_before_001_TIMESTAMP staff.db

This script is provided as an alternative rollback method.
"""

import sqlite3
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def get_db_path():
    """Get the database path"""
    if os.path.exists('/app/staff.db'):
        return '/app/staff.db'
    elif os.path.exists('staff.db'):
        return 'staff.db'
    elif os.path.exists('../staff.db'):
        return '../staff.db'
    else:
        raise Exception("Cannot find staff.db")


def backup_database(db_path):
    """Create backup before rollback"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{db_path}.backup_before_rollback_{timestamp}"

    print(f"📦 Creating backup: {backup_path}")

    conn = sqlite3.connect(db_path)
    backup_conn = sqlite3.connect(backup_path)
    conn.backup(backup_conn)
    backup_conn.close()
    conn.close()

    print(f"✅ Backup created")
    return backup_path


def recreate_provider_table(conn):
    """Recreate the Provider table"""
    print("\n🔧 Recreating Provider table...")

    cursor = conn.cursor()

    # Create Provider table schema
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS providers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Populate from Faculty table (moonlighters only)
    cursor.execute("""
        INSERT INTO providers (id, name, email)
        SELECT id, name, email
        FROM faculty
        WHERE moonlighter = 1
    """)

    provider_count = cursor.rowcount
    print(f"   ✅ Created Provider table with {provider_count} records")

    conn.commit()


def update_foreign_keys_back(conn):
    """Update foreign keys back to providers table"""
    print("\n🔗 Updating foreign keys back to providers...")

    cursor = conn.cursor()

    # Get current data
    cursor.execute("SELECT * FROM signups")
    signups_data = cursor.fetchall()

    cursor.execute("SELECT * FROM assignments")
    assignments_data = cursor.fetchall()

    # Get schemas
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='signups'")
    signups_schema = cursor.fetchone()[0]

    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='assignments'")
    assignments_schema = cursor.fetchone()[0]

    # Recreate signups table
    cursor.execute("DROP TABLE IF EXISTS signups_new")

    new_signups_schema = signups_schema.replace(
        'FOREIGN KEY(provider_id) REFERENCES faculty(id)',
        'FOREIGN KEY(provider_id) REFERENCES providers(id)'
    )

    cursor.execute(new_signups_schema.replace('CREATE TABLE signups', 'CREATE TABLE signups_new'))

    if signups_data:
        placeholders = ','.join(['?' for _ in signups_data[0]])
        cursor.executemany(f"INSERT INTO signups_new VALUES ({placeholders})", signups_data)

    # Recreate assignments table
    cursor.execute("DROP TABLE IF EXISTS assignments_new")

    new_assignments_schema = assignments_schema.replace(
        'FOREIGN KEY(provider_id) REFERENCES faculty(id)',
        'FOREIGN KEY(provider_id) REFERENCES providers(id)'
    )

    cursor.execute(new_assignments_schema.replace('CREATE TABLE assignments', 'CREATE TABLE assignments_new'))

    if assignments_data:
        placeholders = ','.join(['?' for _ in assignments_data[0]])
        cursor.executemany(f"INSERT INTO assignments_new VALUES ({placeholders})", assignments_data)

    # Swap tables
    cursor.execute("DROP TABLE signups")
    cursor.execute("ALTER TABLE signups_new RENAME TO signups")

    cursor.execute("DROP TABLE assignments")
    cursor.execute("ALTER TABLE assignments_new RENAME TO assignments")

    conn.commit()
    print("   ✅ Foreign keys restored to providers")


def run_rollback(db_path=None):
    """Execute the rollback"""
    print("=" * 60)
    print("🔄 Starting Rollback: Restore Provider Table")
    print("=" * 60)

    if not db_path:
        db_path = get_db_path()

    print(f"📂 Database: {db_path}")

    # Create backup
    backup_path = backup_database(db_path)

    # Connect
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")

    try:
        # Check if Provider table already exists
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='providers'")
        if cursor.fetchone():
            print("\n⚠️  Provider table already exists!")
            print("   Skipping rollback - system may already be rolled back")
            conn.close()
            return False

        # Recreate Provider table
        recreate_provider_table(conn)

        # Update foreign keys
        update_foreign_keys_back(conn)

        # Re-enable foreign keys
        conn.execute("PRAGMA foreign_keys = ON")

        # Verify
        cursor.execute("SELECT COUNT(*) FROM providers")
        provider_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM signups")
        signup_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM assignments")
        assignment_count = cursor.fetchone()[0]

        print("\n✅ Rollback completed successfully")
        print(f"   - Providers: {provider_count}")
        print(f"   - Signups: {signup_count}")
        print(f"   - Assignments: {assignment_count}")

        conn.close()

        print("\n⚠️  IMPORTANT: You must also revert code changes:")
        print("   1. git revert HEAD")
        print("   2. git push")
        print("   3. fly deploy")

        return True

    except Exception as e:
        print(f"\n❌ Rollback failed: {e}")
        print(f"   Restore from backup: {backup_path}")
        try:
            conn.close()
        except:
            pass
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Rollback Migration 001')
    parser.add_argument('--db', help='Path to database file', default=None)

    args = parser.parse_args()

    print("\n⚠️  WARNING: This will recreate the Provider table!")
    print("   Alternative: Restore from backup file instead")
    print("   Backup files: staff.db.backup_before_001_*")
    print()

    response = input("Continue with rollback? (yes/no): ")
    if response.lower() != 'yes':
        print("Aborted")
        sys.exit(1)

    success = run_rollback(args.db)
    sys.exit(0 if success else 1)
