"""
Database migration to add service_preference column to unavailability_requests table.

This migration adds support for faculty to specify their service type preferences
(e.g., "Prefer MICU", "Available for Procedures", etc.) when requesting weeks.

Run this script manually or via psql:

    python backend/migrations/add_service_preference.py

Or directly in psql:

    ALTER TABLE unavailability_requests ADD COLUMN IF NOT EXISTS service_preference TEXT;
"""

import sys
from pathlib import Path

# Add parent directory to path to import from backend
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from models import get_db
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    """Add service_preference column to unavailability_requests table."""

    db = next(get_db())

    try:
        logger.info("Starting migration: add service_preference column")

        # Detect database type
        db_url = str(db.bind.url)
        is_sqlite = 'sqlite' in db_url.lower()
        is_postgres = 'postgres' in db_url.lower()

        logger.info(f"Detected database: {'SQLite' if is_sqlite else 'PostgreSQL' if is_postgres else 'Unknown'}")

        # Check if column already exists (database-specific)
        if is_sqlite:
            # SQLite: Use PRAGMA table_info
            check_query = text("PRAGMA table_info(unavailability_requests)")
            result = db.execute(check_query).fetchall()
            column_exists = any(row[1] == 'service_preference' for row in result)
        else:
            # PostgreSQL: Use information_schema
            check_query = text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'unavailability_requests'
                AND column_name = 'service_preference'
            """)
            result = db.execute(check_query).fetchone()
            column_exists = result is not None

        if column_exists:
            logger.info("✓ Column 'service_preference' already exists. Skipping migration.")
            return

        # Add the column (works for both SQLite and PostgreSQL)
        logger.info("Adding 'service_preference' column...")
        migration_query = text("""
            ALTER TABLE unavailability_requests
            ADD COLUMN service_preference TEXT;
        """)

        db.execute(migration_query)
        db.commit()

        logger.info("✓ Successfully added 'service_preference' column to unavailability_requests table")
        logger.info("✓ Migration complete!")

    except Exception as e:
        db.rollback()
        logger.error(f"✗ Migration failed: {e}")
        raise

    finally:
        db.close()


if __name__ == "__main__":
    run_migration()
