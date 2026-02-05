#!/usr/bin/env python3
"""
Migration Script: Move Sessions from In-Memory to Database

This script updates backend/auth.py to use the SessionToken model
instead of the in-memory active_sessions dictionary.

SAFETY: This is a code-only change. No data migration needed.
Users will simply need to log in again after deployment.
"""

import os
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

def create_session_db_auth():
    """Generate new auth.py with database-backed sessions"""

    new_auth_content = '''"""
Authentication utilities for faculty login system.
Provides password hashing, session management, and authentication dependencies.

Uses database-backed SessionToken model for persistent sessions.
"""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session
from .models import Faculty, SessionToken, get_db
from .config import settings
import logging
import secrets
import bcrypt

logger = logging.getLogger(__name__)

# HTTP Basic Auth (for initial testing, we'll use sessions in production)
security = HTTPBasic()


# ==========================================
# PASSWORD UTILITIES
# ==========================================

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False


# ==========================================
# SESSION MANAGEMENT (DATABASE-BACKED)
# ==========================================

def create_session_token() -> str:
    """Generate a secure random session token."""
    return secrets.token_urlsafe(32)


def create_session(
    faculty_id: str,
    faculty_name: str,
    is_admin: bool,
    db: Session,
    request: Request = None,
    impersonated_by: Optional[str] = None
) -> str:
    """Create a new session in database and return the session token.

    Args:
        faculty_id: ID of the faculty member
        faculty_name: Name of the faculty member
        is_admin: Whether the faculty member is an admin
        db: Database session
        request: FastAPI request for IP/user agent tracking
        impersonated_by: Optional faculty ID of the admin who is impersonating this user
    """
    token = create_session_token()

    # Calculate expiration times
    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=settings.SESSION_TIMEOUT_MINUTES)

    # Extract request metadata
    ip_address = request.client.host if request and request.client else None
    user_agent = request.headers.get("user-agent") if request else None

    # Create session record
    session_record = SessionToken(
        session_id=token,
        faculty_id=faculty_id,
        created_at=now,
        last_activity=now,
        expires_at=expires_at,
        ip_address=ip_address,
        user_agent=user_agent,
        invalidated=False
    )

    db.add(session_record)
    db.commit()

    logger.info(f"Created session for {faculty_id} (impersonated_by: {impersonated_by})")

    return token


def get_session(token: str, db: Session) -> Optional[dict]:
    """Get session data from token and update last activity.

    Returns dict with session data or None if invalid/expired.
    """
    session = db.query(SessionToken).filter_by(
        session_id=token,
        invalidated=False
    ).first()

    if not session:
        return None

    now = datetime.utcnow()

    # Check if session is expired
    if now > session.expires_at:
        # Mark as invalidated
        session.invalidated = True
        session.invalidated_at = now
        db.commit()
        logger.info(f"Session {token[:8]}... expired for {session.faculty_id}")
        return None

    # Update last activity
    session.last_activity = now
    db.commit()

    # Return session data (compatible with old in-memory format)
    return {
        "faculty_id": session.faculty_id,
        "faculty_name": None,  # Will be loaded from Faculty table
        "is_admin": None,  # Will be loaded from Faculty table
        "created_at": session.created_at,
        "last_activity": session.last_activity,
        "impersonated_by": None  # TODO: Add to SessionToken model if needed
    }


def delete_session(token: str, db: Session):
    """Invalidate a session."""
    session = db.query(SessionToken).filter_by(session_id=token).first()

    if session:
        session.invalidated = True
        session.invalidated_at = datetime.utcnow()
        db.commit()
        logger.info(f"Invalidated session for {session.faculty_id}")


def cleanup_expired_sessions(db: Session) -> int:
    """Delete expired sessions from database.

    Returns count of deleted sessions.
    """
    cutoff = datetime.utcnow()

    # Delete sessions that are expired or invalidated
    expired = db.query(SessionToken).filter(
        (SessionToken.expires_at < cutoff) | (SessionToken.invalidated == True)
    ).all()

    count = len(expired)

    for session in expired:
        db.delete(session)

    db.commit()
    logger.info(f"Cleaned up {count} expired/invalidated sessions")

    return count


def authenticate_faculty(faculty_id: str, password: str, db: Session) -> Optional[Faculty]:
    """Authenticate a faculty member by ID and password."""
    faculty = db.query(Faculty).filter_by(id=faculty_id.upper()).first()
    if not faculty:
        return None

    if not verify_password(password, faculty.password_hash):
        return None

    if not faculty.active:
        return None

    return faculty


# ==========================================
# FASTAPI DEPENDENCIES (CORE)
# ==========================================

async def get_current_user(request: Request, db: Session = Depends(get_db)) -> Faculty:
    """Get the currently authenticated user from session cookie."""
    # Check for session token in cookies
    session_token = request.cookies.get("session_token")

    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get session data from database
    session = get_session(session_token, db)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get faculty from database
    faculty = db.query(Faculty).filter_by(id=session["faculty_id"]).first()
    if not faculty or not faculty.active:
        delete_session(session_token, db)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or inactive"
        )

    return faculty


async def get_optional_user(request: Request, db: Session = Depends(get_db)) -> Optional[Faculty]:
    """Get the current user if authenticated, None otherwise (no exception)."""
    session_token = request.cookies.get("session_token")

    if not session_token:
        return None

    session = get_session(session_token, db)
    if not session:
        return None

    faculty = db.query(Faculty).filter_by(id=session["faculty_id"]).first()
    if not faculty or not faculty.active:
        return None

    return faculty


# ==========================================
# FASTAPI DEPENDENCIES (SECURITY ENHANCED)
# ==========================================

def require_admin(current_user: Faculty = Depends(get_current_user)) -> Faculty:
    """
    Dependency that requires admin privileges.
    Raises 403 if user is not admin.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user


def optional_require_admin(
    current_user: Optional[Faculty] = Depends(get_optional_user)
) -> Optional[Faculty]:
    """
    Optionally require admin - for transitional period.
    Returns None if no auth, raises 403 if auth but not admin.
    """
    if settings.SECURITY_MODE == "strict":
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        if not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Admin privileges required")
        return current_user

    if settings.SECURITY_MODE == "transitional":
        # Warn but allow access
        if not current_user:
            logger.warning("Unauthenticated admin access in transitional mode")
            return None
        if not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Admin privileges required")
        return current_user

    # Permissive mode - allow everything
    return current_user


# ==========================================
# SECURITY ENHANCED FUNCTIONS
# ==========================================

def check_account_locked(faculty: Faculty) -> None:
    """Check if account is locked due to failed login attempts"""
    if faculty.account_locked_until:
        if datetime.utcnow() < faculty.account_locked_until:
            remaining = (faculty.account_locked_until - datetime.utcnow()).seconds // 60
            raise HTTPException(
                status_code=403,
                detail=f"Account locked. Try again in {remaining} minutes."
            )
        else:
            # Unlock account
            faculty.account_locked_until = None
            faculty.failed_login_attempts = 0


def handle_failed_login(db: Session, faculty: Faculty) -> None:
    """Handle failed login attempt"""
    faculty.failed_login_attempts += 1

    # Lock account after 5 failed attempts
    if faculty.failed_login_attempts >= 5:
        faculty.account_locked_until = datetime.utcnow() + timedelta(minutes=30)
        logger.warning(f"Account locked for {faculty.id} after {faculty.failed_login_attempts} failed attempts")

    db.commit()


def handle_successful_login(db: Session, faculty: Faculty, request: Request) -> None:
    """Handle successful login"""
    faculty.failed_login_attempts = 0
    faculty.account_locked_until = None
    faculty.last_login_at = datetime.utcnow()
    faculty.last_login_ip = request.client.host if request.client else None
    db.commit()
'''

    return new_auth_content


def update_auth_routes():
    """Generate updated auth routes that pass db to session functions"""

    routes_auth_updates = '''
# In backend/routes/auth.py

# Update login endpoint (around line 98):

@router.post("/login", response_model=LoginResponse)
async def login(
    credentials: LoginRequest,
    response: Response,
    request: Request,  # ADD THIS
    db: Session = Depends(get_db)
):
    """
    Authenticate faculty member and create session.
    Returns session cookie.

    The 'username' field is used as the faculty_id for lookup.
    """
    # Authenticate user (username is the faculty_id)
    faculty = authenticate_faculty(
        credentials.username,
        credentials.password,
        db
    )

    if not faculty:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid faculty ID or password"
        )

    # Create session - PASS db AND request
    session_token = create_session(
        faculty.id,
        faculty.name,
        faculty.is_admin,
        db,  # ADD THIS
        request  # ADD THIS
    )

    # Set session cookie (httponly for security)
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        max_age=86400,  # 24 hours
        samesite="lax"
    )

    return LoginResponse(
        message="Login successful",
        faculty_id=faculty.id,
        faculty_name=faculty.name,
        is_admin=faculty.is_admin
    )


# Update logout endpoint (around line 123):

@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)  # ADD THIS
):
    """
    Logout current user and destroy session.
    """
    session_token = request.cookies.get("session_token")

    if session_token:
        delete_session(session_token, db)  # ADD db PARAMETER

    # Clear session cookie
    response.delete_cookie("session_token")

    return {"message": "Logout successful"}


# Update check_auth endpoint (around line 161):

@router.get("/check")
async def check_auth(
    request: Request,
    db: Session = Depends(get_db),  # ADD THIS
    current_user: Optional[Faculty] = Depends(get_optional_user)
):
    if current_user:
        # Check if impersonating
        session_token = request.cookies.get("session_token")
        from backend.auth import get_session
        session = get_session(session_token, db) if session_token else None  # ADD db
        impersonated_by = session.get("impersonated_by") if session else None

        return {
            "authenticated": True,
            "faculty_id": current_user.id,
            "faculty_name": current_user.name,
            "is_admin": current_user.is_admin,
            "is_impersonating": bool(impersonated_by)
        }
    else:
        return {"authenticated": False}
'''

    return routes_auth_updates


def main():
    """Execute migration"""
    print("=" * 70)
    print("SESSION MIGRATION TO DATABASE")
    print("=" * 70)
    print()
    print("This migration will update backend/auth.py to use database-backed")
    print("sessions instead of in-memory dictionary.")
    print()
    print("IMPACT:")
    print("  - All current sessions will be invalidated")
    print("  - Users will need to log in again after deployment")
    print("  - Sessions will persist across server restarts")
    print()
    print("SAFETY:")
    print("  - No data loss (sessions are temporary by nature)")
    print("  - Easily reversible (git checkout backend/auth.py)")
    print("  - SessionToken table already exists in database")
    print()

    response = input("Continue? (yes/no): ")
    if response.lower() != "yes":
        print("Migration cancelled.")
        return

    print()
    print("Generating new auth.py...")

    # Create new auth.py
    new_auth = create_session_db_auth()

    # Backup existing auth.py
    auth_file = backend_path / "auth.py"
    backup_file = backend_path / "auth.py.before_session_migration"

    if auth_file.exists():
        print(f"Backing up existing auth.py to {backup_file}")
        with open(backup_file, 'w') as f:
            f.write(auth_file.read_text())

    # Write new auth.py
    print(f"Writing new auth.py...")
    with open(auth_file, 'w') as f:
        f.write(new_auth)

    print()
    print("✅ Auth.py updated successfully!")
    print()
    print("NEXT STEPS:")
    print()
    print("1. Update backend/routes/auth.py with the changes shown in:")
    print("   migrations/routes_auth_updates.txt")
    print()
    print("2. Test on test instance:")
    print("   cd backend && uvicorn app:app --port 8001")
    print()
    print("3. Try logging in at http://localhost:8001/login.html")
    print()
    print("4. Check that sessions persist after restart:")
    print("   - Log in")
    print("   - Restart server")
    print("   - Refresh page (should still be logged in)")
    print()
    print("5. If everything works, deploy to production")
    print()
    print("ROLLBACK:")
    print("If something goes wrong:")
    print(f"  cp {backup_file} {auth_file}")
    print("  # Then restart server")
    print()

    # Write routes update instructions
    routes_file = Path(__file__).parent / "routes_auth_updates.txt"
    with open(routes_file, 'w') as f:
        f.write(update_auth_routes())

    print(f"Route updates saved to: {routes_file}")
    print()


if __name__ == "__main__":
    main()
