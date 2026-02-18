"""
Add draft_exempt column to faculty table.
This column was added to the SQLAlchemy model but never migrated
into existing databases, so the toggle never persisted.
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from models import engine


def run_migration():
    with engine.connect() as conn:
        # Check if column already exists (SQLite doesn't have IF NOT EXISTS for ALTER TABLE)
        result = conn.execute(text("PRAGMA table_info(faculty)"))
        columns = [row[1] for row in result.fetchall()]

        if "draft_exempt" not in columns:
            conn.execute(text("ALTER TABLE faculty ADD COLUMN draft_exempt BOOLEAN NOT NULL DEFAULT 0"))
            conn.commit()
            print("✅ Added draft_exempt column to faculty table")
        else:
            print("ℹ️  draft_exempt column already exists, skipping")


if __name__ == "__main__":
    run_migration()
