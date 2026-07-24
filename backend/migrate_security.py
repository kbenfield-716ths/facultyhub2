# backend/migrate_security.py
"""
Database migration script - standalone version
Run from backend directory: python3 migrate_security.py
"""

import sqlite3
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def find_database():
    """Find the correct database file"""
    possible_paths = [
        Path("/data/staff.db"),  # Production
        Path(__file__).parent.parent / "staff.db",  # Development default
        Path(__file__).parent.parent / "faculty_hub.db",  # Alternative name
        Path(__file__).parent / "staff.db",  # In backend dir
        Path(__file__).parent / "faculty_hub.db",  # In backend dir
    ]
    
    for path in possible_paths:
        if path.exists():
            # Verify it has the faculty table
            try:
                conn = sqlite3.connect(path)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='faculty'")
                if cursor.fetchone():
                    conn.close()
                    logger.info(f"Found database with faculty table: {path}")
                    return path
                conn.close()
            except Exception as e:
                logger.debug(f"Error checking {path}: {e}")
                continue
    
    return None

def migrate_database():
    """Add new tables and columns for security features"""
    
    # Find the database
    db_path = find_database()
    
    if not db_path:
        logger.error("Could not find database with faculty table!")
        logger.error("\nSearched for:")
        logger.error("  - /data/staff.db")
        logger.error("  - ./staff.db")
        logger.error("  - ./faculty_hub.db")
        logger.error("\nPlease ensure your database exists and has a 'faculty' table.")
        
        # List available .db files
        project_root = Path(__file__).parent.parent
        db_files = list(project_root.glob("*.db"))
        if db_files:
            logger.info("\nFound .db files:")
            for f in db_files:
                logger.info(f"  - {f}")
                # Show tables in each
                try:
                    conn = sqlite3.connect(f)
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tables = [row[0] for row in cursor.fetchall()]
                    logger.info(f"    Tables: {', '.join(tables)}")
                    conn.close()
                except Exception as e:
                    logger.info(f"    Error reading: {e}")
        return
    
    logger.info(f"Migrating database at: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # First, check what tables already exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = [row[0] for row in cursor.fetchall()]
        logger.info(f"Existing tables: {', '.join(existing_tables)}")
        
        # Create audit_logs table
        logger.info("\nCreating audit_logs table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                user_id VARCHAR NOT NULL,
                user_name VARCHAR NOT NULL,
                action VARCHAR NOT NULL,
                resource_type VARCHAR,
                resource_id VARCHAR,
                details TEXT,
                ip_address VARCHAR,
                user_agent VARCHAR
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_timestamp ON audit_logs(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_user_id ON audit_logs(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_action ON audit_logs(action)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_resource_type ON audit_logs(resource_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_timestamp_user ON audit_logs(timestamp, user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_action_resource ON audit_logs(action, resource_type)")
        logger.info("✓ audit_logs table created")
        
        # Create session_tokens table
        logger.info("Creating session_tokens table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS session_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id VARCHAR UNIQUE NOT NULL,
                faculty_id VARCHAR NOT NULL,
                created_at DATETIME NOT NULL,
                last_activity DATETIME NOT NULL,
                expires_at DATETIME NOT NULL,
                ip_address VARCHAR,
                user_agent VARCHAR,
                invalidated BOOLEAN DEFAULT 0,
                invalidated_at DATETIME
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_session_tokens_session_id ON session_tokens(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_session_tokens_faculty_id ON session_tokens(faculty_id)")
        logger.info("✓ session_tokens table created")
        
        # Create password_reset_tokens table
        logger.info("Creating password_reset_tokens table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                faculty_id VARCHAR NOT NULL,
                token VARCHAR UNIQUE NOT NULL,
                created_at DATETIME NOT NULL,
                expires_at DATETIME NOT NULL,
                used BOOLEAN DEFAULT 0,
                used_at DATETIME
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_faculty_id ON password_reset_tokens(faculty_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_token ON password_reset_tokens(token)")
        logger.info("✓ password_reset_tokens table created")
        
        # Check current faculty table structure
        logger.info("\nChecking faculty table structure...")
        cursor.execute("PRAGMA table_info(faculty)")
        existing_columns = [row[1] for row in cursor.fetchall()]
        logger.info(f"Existing columns: {', '.join(existing_columns)}")
        
        # Add new columns to faculty table
        logger.info("\nAdding security columns to faculty table...")
        new_columns = [
            ("password_reset_required", "BOOLEAN DEFAULT 0"),
            ("password_last_changed", "DATETIME"),
            ("failed_login_attempts", "INTEGER DEFAULT 0"),
            ("account_locked_until", "DATETIME"),
            ("last_login_at", "DATETIME"),
            ("last_login_ip", "VARCHAR(50)")
        ]
        
        for col_name, col_def in new_columns:
            if col_name in existing_columns:
                logger.info(f"  Column faculty.{col_name} already exists, skipping")
                continue
                
            try:
                cursor.execute(f"ALTER TABLE faculty ADD COLUMN {col_name} {col_def}")
                logger.info(f"✓ Added column: faculty.{col_name}")
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e).lower():
                    logger.info(f"  Column faculty.{col_name} already exists, skipping")
                else:
                    logger.error(f"✗ Error adding column {col_name}: {e}")
        
        # Update existing faculty
        cursor.execute("UPDATE faculty SET password_reset_required = 1 WHERE password_changed = 0")
        count = cursor.rowcount
        logger.info(f"\n✓ Marked {count} existing users for password reset")
        
        conn.commit()
        
        # Verify tables were created
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        logger.info("\n" + "="*60)
        logger.info("✅ Migration completed successfully!")
        logger.info("="*60)
        logger.info(f"\nDatabase: {db_path}")
        logger.info(f"Tables found: {len(tables)}")
        
        # Verify new tables exist
        if 'audit_logs' in tables:
            logger.info("  ✓ audit_logs")
        if 'session_tokens' in tables:
            logger.info("  ✓ session_tokens")
        if 'password_reset_tokens' in tables:
            logger.info("  ✓ password_reset_tokens")
        
        # Check faculty table columns again
        cursor.execute("PRAGMA table_info(faculty)")
        columns = [row[1] for row in cursor.fetchall()]
        security_cols = ['password_reset_required', 'password_last_changed', 
                        'failed_login_attempts', 'account_locked_until',
                        'last_login_at', 'last_login_ip']
        
        logger.info("\nFaculty table security columns:")
        for col in security_cols:
            if col in columns:
                logger.info(f"  ✓ {col}")
            else:
                logger.warning(f"  ✗ {col} (missing)")
        
        logger.info("\n" + "="*60)
        logger.info("NEXT STEPS:")
        logger.info("1. Review .env file and set SECURITY_MODE=permissive")
        logger.info("2. Start the application:")
        logger.info("   cd ..")
        logger.info("   uvicorn backend.app:app --reload")
        logger.info("3. Test login and password change functionality")
        logger.info("4. Monitor startup logs for generated admin password")
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"\n❌ Migration failed: {e}")
        logger.error("Rolling back changes...")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_database()
