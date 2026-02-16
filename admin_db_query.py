#!/usr/bin/env python3
"""
Admin Database Query Tool
Execute SQL queries against the Faculty Hub database.

Usage:
    python3 admin_db_query.py

Features:
    - Execute custom SQL queries
    - Pre-built common queries
    - View table structure
    - Export results to CSV
    - Safe read-only mode by default

⚠️  Use with caution! This provides direct database access.
"""

import sqlite3
from pathlib import Path
from datetime import datetime
import sys
import csv
from typing import Optional, List, Tuple


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


def display_results(cursor: sqlite3.Cursor, results: List[Tuple]):
    """Display query results in a formatted table"""
    if not results:
        print("\n📭 No results returned.")
        return

    # Get column names
    columns = [description[0] for description in cursor.description]

    # Calculate column widths
    widths = [len(col) for col in columns]
    for row in results:
        for i, val in enumerate(row):
            val_str = str(val) if val is not None else "NULL"
            widths[i] = max(widths[i], len(val_str))

    # Print header
    print()
    header = " | ".join(col.ljust(widths[i]) for i, col in enumerate(columns))
    print(header)
    print("-" * len(header))

    # Print rows
    for row in results:
        row_str = " | ".join(
            str(val).ljust(widths[i]) if val is not None else "NULL".ljust(widths[i])
            for i, val in enumerate(row)
        )
        print(row_str)

    print()
    print(f"📊 {len(results)} row(s) returned")


def export_to_csv(cursor: sqlite3.Cursor, results: List[Tuple], filename: str):
    """Export results to CSV file"""
    try:
        columns = [description[0] for description in cursor.description]

        with open(filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(columns)
            writer.writerows(results)

        print(f"\n✅ Results exported to: {filename}")

    except Exception as e:
        print(f"\n❌ Export failed: {e}")


def list_tables(cursor: sqlite3.Cursor):
    """List all tables in the database"""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cursor.fetchall()

    print("\n📋 Database Tables:")
    print("-" * 50)
    for table in tables:
        print(f"  • {table[0]}")
    print("-" * 50)
    print(f"\n{len(tables)} table(s) found")


def describe_table(cursor: sqlite3.Cursor, table_name: str):
    """Show table structure"""
    try:
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()

        if not columns:
            print(f"\n❌ Table '{table_name}' not found")
            return

        print(f"\n📋 Structure of table '{table_name}':")
        print("-" * 70)
        print(f"{'Column':<25} {'Type':<15} {'NotNull':<10} {'Default':<15}")
        print("-" * 70)

        for col in columns:
            col_name = col[1]
            col_type = col[2]
            not_null = "YES" if col[3] else "NO"
            default = col[4] if col[4] is not None else ""
            print(f"{col_name:<25} {col_type:<15} {not_null:<10} {str(default):<15}")

        print("-" * 70)

        # Show indexes
        cursor.execute(f"PRAGMA index_list({table_name})")
        indexes = cursor.fetchall()

        if indexes:
            print(f"\n🔑 Indexes on '{table_name}':")
            for idx in indexes:
                print(f"  • {idx[1]} (unique: {bool(idx[2])})")

    except sqlite3.Error as e:
        print(f"\n❌ Error: {e}")


def run_common_queries(cursor: sqlite3.Cursor):
    """Execute common pre-built queries"""
    queries = {
        "1": {
            "name": "All active users",
            "sql": "SELECT id, name, email, is_admin, last_login_at FROM faculty WHERE active = 1 ORDER BY name"
        },
        "2": {
            "name": "All inactive users",
            "sql": "SELECT id, name, email, is_admin FROM faculty WHERE active = 0 ORDER BY name"
        },
        "3": {
            "name": "All admin users",
            "sql": "SELECT id, name, email, active FROM faculty WHERE is_admin = 1 ORDER BY name"
        },
        "4": {
            "name": "Locked accounts",
            "sql": "SELECT id, name, email, failed_login_attempts, account_locked_until FROM faculty WHERE account_locked_until IS NOT NULL ORDER BY name"
        },
        "5": {
            "name": "Users who haven't changed password",
            "sql": "SELECT id, name, email, registered FROM faculty WHERE password_changed = 0 ORDER BY name"
        },
        "6": {
            "name": "Recent login activity (last 7 days)",
            "sql": """
                SELECT id, name, email, last_login_at, last_login_ip
                FROM faculty
                WHERE last_login_at IS NOT NULL
                  AND last_login_at >= datetime('now', '-7 days')
                ORDER BY last_login_at DESC
            """
        },
        "7": {
            "name": "Users with failed login attempts",
            "sql": "SELECT id, name, email, failed_login_attempts FROM faculty WHERE failed_login_attempts > 0 ORDER BY failed_login_attempts DESC"
        },
        "8": {
            "name": "Moonlighting participants",
            "sql": "SELECT id, name, email, active FROM faculty WHERE moonlighter = 1 ORDER BY name"
        },
        "9": {
            "name": "Faculty by rank",
            "sql": "SELECT rank, COUNT(*) as count FROM faculty WHERE active = 1 GROUP BY rank ORDER BY count DESC"
        },
        "10": {
            "name": "Active sessions",
            "sql": "SELECT session_id, faculty_id, created_at, last_activity, expires_at, invalidated FROM session_tokens WHERE invalidated = 0 ORDER BY last_activity DESC"
        }
    }

    print("\n" + "=" * 70)
    print("Common Queries")
    print("=" * 70)

    for key, query in queries.items():
        print(f"  {key}. {query['name']}")

    print()
    choice = input("Select query (or press Enter to cancel): ").strip()

    if choice in queries:
        query = queries[choice]
        print(f"\n🔍 Running: {query['name']}")
        print(f"📝 SQL: {query['sql'][:100]}{'...' if len(query['sql']) > 100 else ''}")

        try:
            cursor.execute(query['sql'])
            results = cursor.fetchall()
            display_results(cursor, results)

            if results and input("\nExport to CSV? (yes/no): ").strip().lower() in ['yes', 'y']:
                filename = f"query_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                export_to_csv(cursor, results, filename)

        except sqlite3.Error as e:
            print(f"\n❌ Query error: {e}")


def execute_custom_query(cursor: sqlite3.Cursor, read_only: bool = True):
    """Execute a custom SQL query"""
    print("\n" + "=" * 70)
    print("Custom SQL Query")
    print("=" * 70)

    if read_only:
        print("\n⚠️  READ-ONLY MODE: Only SELECT queries allowed")
    else:
        print("\n⚠️  WRITE MODE ENABLED: Use with extreme caution!")

    print("\nEnter your SQL query (or 'cancel' to go back):")
    print("Tip: For multi-line queries, end with ';' on its own line")

    query_lines = []
    while True:
        line = input("SQL> " if not query_lines else "...> ").strip()

        if line.lower() == 'cancel':
            return

        query_lines.append(line)

        if line.endswith(';'):
            break

    query = ' '.join(query_lines)

    # Check for write operations in read-only mode
    if read_only:
        write_keywords = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'CREATE', 'TRUNCATE']
        query_upper = query.upper()

        for keyword in write_keywords:
            if keyword in query_upper:
                print(f"\n❌ {keyword} operations not allowed in read-only mode!")
                print("   Enable write mode from the main menu to execute this query.")
                return

    print(f"\n🔍 Executing query...")

    try:
        cursor.execute(query)

        # Check if query returns results
        if cursor.description:
            results = cursor.fetchall()
            display_results(cursor, results)

            if results and input("\nExport to CSV? (yes/no): ").strip().lower() in ['yes', 'y']:
                filename = f"query_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                export_to_csv(cursor, results, filename)
        else:
            # No results (likely INSERT, UPDATE, DELETE)
            if not read_only:
                rows_affected = cursor.rowcount
                print(f"\n✅ Query executed successfully. {rows_affected} row(s) affected.")
            else:
                print("\n✅ Query executed successfully.")

    except sqlite3.Error as e:
        print(f"\n❌ Query error: {e}")


def interactive_query(conn: sqlite3.Connection, cursor: sqlite3.Cursor):
    """Interactive query interface"""
    read_only = True

    while True:
        print("\n" + "=" * 70)
        print("Faculty Hub - Database Query Tool")
        print("=" * 70)
        print(f"\nMode: {'🔒 READ-ONLY' if read_only else '✏️  WRITE ENABLED'}")
        print("\nOptions:")
        print("  1. List all tables")
        print("  2. Describe table structure")
        print("  3. Run common queries")
        print("  4. Execute custom query")
        print("  5. Toggle write mode")
        print("  6. Exit")
        print()

        choice = input("Enter your choice (1-6): ").strip()

        if choice == "1":
            list_tables(cursor)

        elif choice == "2":
            table_name = input("\nEnter table name: ").strip()
            if table_name:
                describe_table(cursor, table_name)

        elif choice == "3":
            run_common_queries(cursor)

        elif choice == "4":
            execute_custom_query(cursor, read_only)

        elif choice == "5":
            if read_only:
                confirm = input("\n⚠️  Enable write mode? This allows INSERT/UPDATE/DELETE operations. (yes/no): ").strip().lower()
                if confirm in ['yes', 'y']:
                    read_only = False
                    print("\n✏️  Write mode ENABLED")
            else:
                read_only = True
                print("\n🔒 Write mode disabled (read-only)")

        elif choice == "6":
            print("\n👋 Goodbye!")
            break

        else:
            print("\n❌ Invalid choice. Please enter 1-6.")


def main():
    """Main function"""
    print("\n" + "=" * 70)
    print("Faculty Hub - Database Query Tool")
    print("=" * 70)

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

        # Run interactive interface
        interactive_query(conn, cursor)

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
