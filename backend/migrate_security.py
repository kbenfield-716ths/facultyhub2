# backend/migrate_security.py
"""
Database migration script to add security tables and fields.
Run this ONCE before deploying security updates.
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from .models import Base, Faculty, AuditLog, SessionToken, PasswordResetToken
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_database():
    """Add new tables and columns for security features"""
    engine = create_engine("sqlite:///./faculty_hub.db")
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        logger.info("Starting database migration...")
        
        # Create new tables
        Base.metadata.create_all(bind=engine)
        logger.info("✓ Created new tables (audit_logs, session_tokens, password_reset_tokens)")
        
        # Add new columns to Faculty table (SQLite doesn't support ALTER COLUMN easily)
        # We'll check if columns exist and add if missing
        
        new_columns = [
            ("password_reset_required", "BOOLEAN DEFAULT 0"),
            ("password_last_changed", "DATETIME"),
            ("failed_login_attempts", "INTEGER DEFAULT 0"),
            ("account_locked_until", "DATETIME"),
            ("last_login_at", "DATETIME"),
            ("last_login_ip", "VARCHAR(50)")
        ]
        
        for col_name, col_def in new_columns:
            try:
                db.execute(text(f"ALTER TABLE faculty ADD COLUMN {col_name} {col_def}"))
                logger.info(f"✓ Added column: faculty.{col_name}")
            except Exception as e:
                if "duplicate column name" in str(e).lower():
                    logger.info(f"  Column faculty.{col_name} already exists, skipping")
                else:
                    logger.error(f"✗ Error adding column {col_name}: {e}")
        
        db.commit()
        
        # Update existing faculty to require password reset
        result = db.execute(text(
            "UPDATE faculty SET password_reset_required = 1 WHERE password_changed = 0"
        ))
        logger.info(f"✓ Marked {result.rowcount} existing users for password reset")
        
        db.commit()
        
        logger.info("Migration completed successfully!")
        logger.info("\nNEXT STEPS:")
        logger.info("1. Review .env file and set SECURITY_MODE")
        logger.info("2. Configure CORS_ORIGINS for production")
        logger.info("3. Test login and password change functionality")
        logger.info("4. Monitor audit logs after deployment")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate_database()
