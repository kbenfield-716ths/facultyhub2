#!/usr/bin/env python3
"""
Admin User Management Tool
Manage faculty user accounts - reset passwords, change usernames, unlock accounts.

Usage:
    python3 admin_user_management.py

Features:
    - Reset password to default (PCCM2025!)
    - Change username/faculty ID
    - Unlock locked accounts
    - Reset failed login attempts
    - Toggle admin status
    - Activate/deactivate accounts
    - Create database backups before changes

⚠️  IMPORTANT: Stop your server before making changes!
"""

import sqlite3
from pathlib import Path
from datetime import datetime
import shutil
import bcrypt
import sys
from typing import Optional, Dict


# Default password for resets
DEFAULT_PASSWORD = "PCCM2025!"


def find_database() -> Optional[Path]:
    """Find the database file"""
    possible_paths = [
        Path("./moonlighter.db"),
        Path("/data/moonlighter.db"),
        Path("../moonlighter.db"),
    ]

    for path in possible_paths:
        if path.exists():
            return path

    return None


def backup_database(db_path: Path) -> Path:
    """Create a backup of the database"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"{db_path.stem}.backup.{timestamp}.db"
    shutil.copy2(db_path, backup_path)
    return backup_path


def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def get_user(cursor: sqlite3.Cursor, faculty_id: str) -> Optional[Dict]:
    """Get user information"""
    cursor.execute("SELECT * FROM faculty WHERE UPPER(id) = ?", (faculty_id.upper(),))
    row = cursor.fetchone()

    if row:
        columns = [description[0] for description in cursor.description]
        return dict(zip(columns, row))

    return None


def display_user_summary(user: Dict):
    """Display brief user summary"""
    print(f"\n  ID: {user['id']}")
    print(f"  Name: {user['name']}")
    print(f"  Email: {user['email']}")
    print(f"  Active: {'✅ Yes' if user['active'] else '❌ No'}")
    print(f"  Admin: {'✅ Yes' if user['is_admin'] else '❌ No'}")


def reset_password(conn: sqlite3.Connection, cursor: sqlite3.Cursor, faculty_id: str) -> bool:
    """Reset a user's password to the default"""
    user = get_user(cursor, faculty_id)

    if not user:
        print(f"\n❌ User not found: {faculty_id}")
        return False

    print("\n📋 User to reset:")
    display_user_summary(user)

    confirm = input(f"\n⚠️  Reset password to '{DEFAULT_PASSWORD}'? (yes/no): ").strip().lower()

    if confirm not in ['yes', 'y']:
        print("❌ Cancelled")
        return False

    try:
        # Generate new password hash
        new_hash = hash_password(DEFAULT_PASSWORD)

        # Update password and reset security fields
        cursor.execute("""
            UPDATE faculty
            SET password_hash = ?,
                password_changed = 0,
                password_reset_required = 0,
                failed_login_attempts = 0,
                account_locked_until = NULL,
                password_last_changed = ?
            WHERE id = ?
        """, (new_hash, datetime.utcnow().isoformat(), user['id']))

        conn.commit()

        print(f"\n✅ Password reset successful!")
        print(f"   Username: {user['id']}")
        print(f"   Password: {DEFAULT_PASSWORD}")
        print(f"\n⚠️  User will be prompted to change password on first login.")

        return True

    except sqlite3.Error as e:
        print(f"\n❌ Database error: {e}")
        conn.rollback()
        return False


def change_username(conn: sqlite3.Connection, cursor: sqlite3.Cursor, old_id: str, new_id: str) -> bool:
    """Change a user's faculty ID (username)"""
    old_user = get_user(cursor, old_id)

    if not old_user:
        print(f"\n❌ User not found: {old_id}")
        return False

    # Check if new ID already exists
    new_user = get_user(cursor, new_id)
    if new_user:
        print(f"\n❌ Faculty ID '{new_id}' already exists!")
        return False

    print("\n📋 User to change:")
    display_user_summary(old_user)

    print(f"\n⚠️  This will change Faculty ID from '{old_id}' to '{new_id}'")
    print("   This affects all related records (signups, assignments, messages, etc.)")
    confirm = input("\nProceed with change? (yes/no): ").strip().lower()

    if confirm not in ['yes', 'y']:
        print("❌ Cancelled")
        return False

    try:
        # Enable foreign key support
        cursor.execute("PRAGMA foreign_keys = OFF")

        # List of tables with faculty_id foreign keys that need updating
        tables_to_update = [
            ('signups', 'provider_id'),
            ('assignments', 'provider_id'),
            ('unavailability_requests', 'faculty_id'),
            ('service_week_assignments', 'faculty_id'),
            ('service_week_assignments', 'created_by'),
            ('faculty_blocks', 'faculty_id'),
            ('faculty_blocks', 'created_by'),
            ('messages', 'author_id'),
            ('message_reactions', 'faculty_id'),
            ('message_read_status', 'faculty_id'),
            ('knowledge_base_articles', 'created_by'),
            ('draft_slots', 'faculty_id'),
            ('session_tokens', 'faculty_id'),
            ('password_reset_tokens', 'faculty_id'),
            ('audit_logs', 'user_id'),
        ]

        print("\n🔄 Updating related records...")

        # Update all foreign key references
        for table, column in tables_to_update:
            try:
                cursor.execute(f"""
                    UPDATE {table}
                    SET {column} = ?
                    WHERE {column} = ?
                """, (new_id.upper(), old_id.upper()))
                rows_affected = cursor.rowcount
                if rows_affected > 0:
                    print(f"   ✅ Updated {rows_affected} records in {table}.{column}")
            except sqlite3.Error as e:
                # Table might not exist or column might not exist - that's okay
                if "no such table" not in str(e).lower() and "no such column" not in str(e).lower():
                    print(f"   ⚠️  Warning updating {table}.{column}: {e}")

        # Update the primary key in faculty table
        cursor.execute("UPDATE faculty SET id = ? WHERE id = ?", (new_id.upper(), old_id.upper()))

        conn.commit()

        # Re-enable foreign key support
        cursor.execute("PRAGMA foreign_keys = ON")

        print(f"\n✅ Username changed successfully!")
        print(f"   Old ID: {old_id}")
        print(f"   New ID: {new_id}")
        print(f"\n⚠️  Make sure to notify the user of their new username!")

        return True

    except sqlite3.Error as e:
        print(f"\n❌ Database error: {e}")
        conn.rollback()
        cursor.execute("PRAGMA foreign_keys = ON")
        return False


def unlock_account(conn: sqlite3.Connection, cursor: sqlite3.Cursor, faculty_id: str) -> bool:
    """Unlock a locked account and reset failed login attempts"""
    user = get_user(cursor, faculty_id)

    if not user:
        print(f"\n❌ User not found: {faculty_id}")
        return False

    print("\n📋 User to unlock:")
    display_user_summary(user)
    print(f"  Failed Login Attempts: {user['failed_login_attempts']}")

    if user['account_locked_until']:
        lock_time = datetime.fromisoformat(user['account_locked_until'].replace('Z', '+00:00'))
        if datetime.utcnow() < lock_time:
            print(f"  Status: 🔒 LOCKED until {lock_time.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            print(f"  Status: Lock expired but not cleared")
    else:
        print(f"  Status: ✅ Not locked")

    confirm = input("\nUnlock account and reset failed login attempts? (yes/no): ").strip().lower()

    if confirm not in ['yes', 'y']:
        print("❌ Cancelled")
        return False

    try:
        cursor.execute("""
            UPDATE faculty
            SET failed_login_attempts = 0,
                account_locked_until = NULL
            WHERE id = ?
        """, (user['id'],))

        conn.commit()

        print(f"\n✅ Account unlocked successfully!")
        print(f"   Failed login attempts reset to 0")
        print(f"   Account lock removed")

        return True

    except sqlite3.Error as e:
        print(f"\n❌ Database error: {e}")
        conn.rollback()
        return False


def toggle_admin(conn: sqlite3.Connection, cursor: sqlite3.Cursor, faculty_id: str) -> bool:
    """Toggle admin status for a user"""
    user = get_user(cursor, faculty_id)

    if not user:
        print(f"\n❌ User not found: {faculty_id}")
        return False

    print("\n📋 User to modify:")
    display_user_summary(user)

    new_status = not user['is_admin']
    action = "grant" if new_status else "revoke"

    confirm = input(f"\n{action.capitalize()} admin privileges? (yes/no): ").strip().lower()

    if confirm not in ['yes', 'y']:
        print("❌ Cancelled")
        return False

    try:
        cursor.execute("UPDATE faculty SET is_admin = ? WHERE id = ?", (new_status, user['id']))
        conn.commit()

        print(f"\n✅ Admin status updated!")
        print(f"   User: {user['name']} ({user['id']})")
        print(f"   Admin: {'✅ Yes' if new_status else '❌ No'}")

        return True

    except sqlite3.Error as e:
        print(f"\n❌ Database error: {e}")
        conn.rollback()
        return False


def toggle_active(conn: sqlite3.Connection, cursor: sqlite3.Cursor, faculty_id: str) -> bool:
    """Toggle active status for a user"""
    user = get_user(cursor, faculty_id)

    if not user:
        print(f"\n❌ User not found: {faculty_id}")
        return False

    print("\n📋 User to modify:")
    display_user_summary(user)

    new_status = not user['active']
    action = "activate" if new_status else "deactivate"

    confirm = input(f"\n{action.capitalize()} account? (yes/no): ").strip().lower()

    if confirm not in ['yes', 'y']:
        print("❌ Cancelled")
        return False

    try:
        cursor.execute("UPDATE faculty SET active = ? WHERE id = ?", (new_status, user['id']))
        conn.commit()

        print(f"\n✅ Account status updated!")
        print(f"   User: {user['name']} ({user['id']})")
        print(f"   Active: {'✅ Yes' if new_status else '❌ No'}")

        return True

    except sqlite3.Error as e:
        print(f"\n❌ Database error: {e}")
        conn.rollback()
        return False


def interactive_management(conn: sqlite3.Connection, cursor: sqlite3.Cursor, db_path: Path):
    """Interactive management interface"""
    while True:
        print("\n" + "=" * 70)
        print("Faculty Hub - User Management Tool")
        print("=" * 70)
        print("\nManagement Options:")
        print("  1. Reset Password (to default)")
        print("  2. Change Username (Faculty ID)")
        print("  3. Unlock Account")
        print("  4. Toggle Admin Status")
        print("  5. Toggle Active Status")
        print("  6. Exit")
        print()

        choice = input("Enter your choice (1-6): ").strip()

        if choice == "1":
            faculty_id = input("\nEnter Faculty ID to reset: ").strip()
            if faculty_id:
                # Create backup before making changes
                print("\n📦 Creating backup...")
                backup_path = backup_database(db_path)
                print(f"✅ Backup created: {backup_path}")

                reset_password(conn, cursor, faculty_id)

        elif choice == "2":
            old_id = input("\nEnter current Faculty ID: ").strip()
            new_id = input("Enter new Faculty ID: ").strip()

            if old_id and new_id:
                # Create backup before making changes
                print("\n📦 Creating backup...")
                backup_path = backup_database(db_path)
                print(f"✅ Backup created: {backup_path}")

                change_username(conn, cursor, old_id, new_id)

        elif choice == "3":
            faculty_id = input("\nEnter Faculty ID to unlock: ").strip()
            if faculty_id:
                unlock_account(conn, cursor, faculty_id)

        elif choice == "4":
            faculty_id = input("\nEnter Faculty ID: ").strip()
            if faculty_id:
                # Create backup before making changes
                print("\n📦 Creating backup...")
                backup_path = backup_database(db_path)
                print(f"✅ Backup created: {backup_path}")

                toggle_admin(conn, cursor, faculty_id)

        elif choice == "5":
            faculty_id = input("\nEnter Faculty ID: ").strip()
            if faculty_id:
                # Create backup before making changes
                print("\n📦 Creating backup...")
                backup_path = backup_database(db_path)
                print(f"✅ Backup created: {backup_path}")

                toggle_active(conn, cursor, faculty_id)

        elif choice == "6":
            print("\n👋 Goodbye!")
            break

        else:
            print("\n❌ Invalid choice. Please enter 1-6.")


def main():
    """Main function"""
    print("\n" + "=" * 70)
    print("Faculty Hub - User Management Tool")
    print("=" * 70)
    print("\n⚠️  WARNING: This tool makes direct database changes!")
    print("⚠️  Make sure your server is STOPPED before proceeding!")
    print()

    proceed = input("Continue? (yes/no): ").strip().lower()
    if proceed not in ['yes', 'y']:
        print("❌ Cancelled")
        sys.exit(0)

    # Find database
    db_path = find_database()

    if not db_path:
        print("\n❌ Could not find database file!")
        print("\nSearched for:")
        print("  - ./moonlighter.db")
        print("  - /data/moonlighter.db")
        print("  - ../moonlighter.db")
        print()

        db_input = input("Enter database path (or press Enter to exit): ").strip()
        if db_input:
            db_path = Path(db_input)
            if not db_path.exists():
                print(f"\n❌ File not found: {db_path}")
                sys.exit(1)
        else:
            sys.exit(1)

    print(f"\n✅ Using database: {db_path}")

    # Connect to database
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if faculty table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='faculty'")
        if not cursor.fetchone():
            print("\n❌ Faculty table not found in database!")
            sys.exit(1)

        # Run interactive management
        interactive_management(conn, cursor, db_path)

    except sqlite3.Error as e:
        print(f"\n❌ Database error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted by user. Goodbye!")
    finally:
        if 'conn' in locals():
            conn.close()


if __name__ == "__main__":
    main()
