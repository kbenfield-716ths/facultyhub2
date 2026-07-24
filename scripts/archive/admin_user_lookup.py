#!/usr/bin/env python3
"""
Admin User Lookup Tool
Query and display faculty user information from the database.

Usage:
    python3 admin_user_lookup.py

Features:
    - Search by faculty ID
    - Search by name (partial match)
    - Search by email
    - View all users
    - Display detailed user information including login status
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
import sys


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


def format_datetime(dt_string: Optional[str]) -> str:
    """Format datetime string for display"""
    if not dt_string:
        return "Never"
    try:
        dt = datetime.fromisoformat(dt_string.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return dt_string


def display_user(user: Dict, detailed: bool = True):
    """Display user information"""
    print("\n" + "=" * 70)
    print(f"Faculty ID: {user['id']}")
    print(f"Name: {user['name']}")
    print(f"Email: {user['email']}")
    print("-" * 70)

    # Authentication status
    print(f"Active: {'✅ Yes' if user['active'] else '❌ No'}")
    print(f"Admin: {'✅ Yes' if user['is_admin'] else '❌ No'}")
    print(f"Registered: {'✅ Yes' if user['registered'] else '❌ No'}")
    print(f"Password Changed: {'✅ Yes' if user['password_changed'] else '❌ No (using default)'}")

    if detailed:
        print("-" * 70)

        # Security info
        print(f"Password Reset Required: {'⚠️  Yes' if user['password_reset_required'] else '✅ No'}")
        print(f"Failed Login Attempts: {user['failed_login_attempts']}")

        if user['account_locked_until']:
            lock_time = datetime.fromisoformat(user['account_locked_until'].replace('Z', '+00:00'))
            if datetime.utcnow() < lock_time:
                print(f"Account Status: 🔒 LOCKED until {format_datetime(user['account_locked_until'])}")
            else:
                print(f"Account Status: ✅ Unlocked (lock expired)")
        else:
            print(f"Account Status: ✅ Unlocked")

        print(f"Last Login: {format_datetime(user['last_login_at'])}")
        print(f"Last Login IP: {user['last_login_ip'] or 'N/A'}")
        print(f"Password Last Changed: {format_datetime(user['password_last_changed'])}")

        print("-" * 70)

        # Profile info
        print(f"Rank: {user['rank']}")
        print(f"Clinical Effort: {user['clinical_effort_pct']}%")
        print(f"Base Points: {user['base_points']}")
        print(f"Bonus Points: {user['bonus_points']}")
        print(f"Moonlighter: {'✅ Yes' if user['moonlighter'] else '❌ No'}")

        print("-" * 70)

        # Service commitments
        print(f"MICU Weeks: {user['micu_weeks']}")
        print(f"APP-ICU Weeks: {user['app_icu_weeks']}")
        print(f"Procedure Weeks: {user['procedure_weeks']}")
        print(f"Consult Weeks: {user['consult_weeks']}")

    print("=" * 70)


def search_by_id(cursor: sqlite3.Cursor, faculty_id: str) -> Optional[Dict]:
    """Search for a user by faculty ID"""
    cursor.execute("SELECT * FROM faculty WHERE UPPER(id) = ?", (faculty_id.upper(),))
    row = cursor.fetchone()

    if row:
        columns = [description[0] for description in cursor.description]
        return dict(zip(columns, row))

    return None


def search_by_name(cursor: sqlite3.Cursor, name: str) -> List[Dict]:
    """Search for users by name (partial match)"""
    cursor.execute(
        "SELECT * FROM faculty WHERE LOWER(name) LIKE ? ORDER BY name",
        (f"%{name.lower()}%",)
    )
    rows = cursor.fetchall()

    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


def search_by_email(cursor: sqlite3.Cursor, email: str) -> Optional[Dict]:
    """Search for a user by email"""
    cursor.execute("SELECT * FROM faculty WHERE LOWER(email) = ?", (email.lower(),))
    row = cursor.fetchone()

    if row:
        columns = [description[0] for description in cursor.description]
        return dict(zip(columns, row))

    return None


def list_all_users(cursor: sqlite3.Cursor) -> List[Dict]:
    """Get all users"""
    cursor.execute("SELECT * FROM faculty ORDER BY name")
    rows = cursor.fetchall()

    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


def interactive_search(cursor: sqlite3.Cursor):
    """Interactive search interface"""
    while True:
        print("\n" + "=" * 70)
        print("Faculty Hub - User Lookup Tool")
        print("=" * 70)
        print("\nSearch Options:")
        print("  1. Search by Faculty ID")
        print("  2. Search by Name")
        print("  3. Search by Email")
        print("  4. List All Users")
        print("  5. Exit")
        print()

        choice = input("Enter your choice (1-5): ").strip()

        if choice == "1":
            faculty_id = input("\nEnter Faculty ID (e.g., KE4Z, IN2C): ").strip()
            user = search_by_id(cursor, faculty_id)

            if user:
                display_user(user, detailed=True)
            else:
                print(f"\n❌ No user found with ID: {faculty_id}")

        elif choice == "2":
            name = input("\nEnter name (partial match OK): ").strip()
            users = search_by_name(cursor, name)

            if users:
                print(f"\n✅ Found {len(users)} user(s):")
                for i, user in enumerate(users, 1):
                    print(f"\n{i}. {user['name']} ({user['id']}) - {user['email']}")

                if len(users) == 1:
                    display_user(users[0], detailed=True)
                else:
                    detail = input("\nView details? Enter number (or press Enter to skip): ").strip()
                    if detail.isdigit() and 1 <= int(detail) <= len(users):
                        display_user(users[int(detail) - 1], detailed=True)
            else:
                print(f"\n❌ No users found matching: {name}")

        elif choice == "3":
            email = input("\nEnter email address: ").strip()
            user = search_by_email(cursor, email)

            if user:
                display_user(user, detailed=True)
            else:
                print(f"\n❌ No user found with email: {email}")

        elif choice == "4":
            users = list_all_users(cursor)

            print(f"\n✅ Total Faculty: {len(users)}")
            print("\n" + "-" * 70)
            print(f"{'ID':<8} {'Name':<30} {'Active':<8} {'Admin':<8}")
            print("-" * 70)

            for user in users:
                active = "✅" if user['active'] else "❌"
                admin = "✅" if user['is_admin'] else "  "
                print(f"{user['id']:<8} {user['name']:<30} {active:<8} {admin:<8}")

            print("-" * 70)

            detail = input("\nView details for a user? Enter Faculty ID (or press Enter to skip): ").strip()
            if detail:
                user = search_by_id(cursor, detail)
                if user:
                    display_user(user, detailed=True)
                else:
                    print(f"\n❌ No user found with ID: {detail}")

        elif choice == "5":
            print("\n👋 Goodbye!")
            break

        else:
            print("\n❌ Invalid choice. Please enter 1-5.")


def main():
    """Main function"""
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

        # Run interactive search
        interactive_search(cursor)

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
