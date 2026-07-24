"""
Multi-division support: divisions table + division_key flags.

  divisions                — new table (key, label, color, is_active)
  faculty.division_key     — which division a user belongs to (null = unassigned)
  knowledge_base_articles.division_key — null = department-wide policy

Idempotent — safe to run more than once.

Usage:  python3 backend/migrations/add_divisions.py [path/to/staff.db]
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parents[2] / "staff.db")


def column_names(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def main():
    conn = sqlite3.connect(DB_PATH)
    try:
        added = []
        conn.execute("""
            CREATE TABLE IF NOT EXISTS divisions (
                key        VARCHAR PRIMARY KEY,
                label      VARCHAR NOT NULL,
                color      VARCHAR,
                is_active  BOOLEAN NOT NULL DEFAULT 1,
                created_at DATETIME
            )
        """)

        if "division_key" not in column_names(conn, "faculty"):
            conn.execute("ALTER TABLE faculty ADD COLUMN division_key VARCHAR REFERENCES divisions(key)")
            conn.execute("CREATE INDEX IF NOT EXISTS ix_faculty_division_key ON faculty(division_key)")
            added.append("faculty.division_key")

        if "division_key" not in column_names(conn, "knowledge_base_articles"):
            conn.execute("ALTER TABLE knowledge_base_articles ADD COLUMN division_key VARCHAR REFERENCES divisions(key)")
            conn.execute("CREATE INDEX IF NOT EXISTS ix_kb_division_key ON knowledge_base_articles(division_key)")
            added.append("knowledge_base_articles.division_key")

        conn.commit()
        print(f"Migrated {DB_PATH}: divisions table ensured; added: {', '.join(added) or 'nothing new'}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
